"""Three ways to paint a person, on the same skeleton and the same clothes, armour and weapons.

The classic figure is built from round capsules; these styles shape the body instead: limbs follow an
anatomical profile (a thigh swells at the front, a calf at the back, a forearm thickens below the elbow and
narrows to the wrist), the torso has a chest, a waist and hips, the head is seen in true profile with a
brow, a nose, lips and a chin, hands are mittens with a thumb and shoes have a heel and a toe.

  storybook  "Bilderbuch" — rounded and friendly, a big expressive eye, warm outlines, soft shading
  ink        "Tusche"     — graphic-novel: realistic proportions, ink outlines, hard cel shadows
  oil        "Ölbild"     — painterly: no outlines, soft three-tone shading, a warm rim of light
  manga      "Manga"      — after the war epics of Japanese comics: lean and tall with a small head, bold
                            tapered ink, hard shadows hatched at the edges, sharp eyes under angled brows,
                            spiky wind-swept hair (some tied in a flowing tail), sashes streaming behind

Every shape (limb, torso, head, hand, shoe) is shaded by one routine: the outline's normals tell which side
faces the light (upper left); the far side gets a shadow crescent, the near side a rim of light.
"""
import math

import pygame

from .paint import LIGHT, warm, mix, shade

ORDER = ("ink", "manga", "storybook", "oil", "classic")
STYLE = ["ink"]


class Style:
    def __init__(self, name, head, outline, ink, shadow, rim, two_tone, blur, eye, build, hatch=False):
        self.name = name
        self.head = head            # head size relative to the skeleton's
        self.outline = outline      # outline width at the final size (px), 0 = none
        self.ink = ink              # outline colour: None = a dark shade of the fill, else this colour
        self.shadow = shadow        # depth of the shadow crescent (fraction of the local width)
        self.rim = rim              # width of the rim of light
        self.two_tone = two_tone    # a soft middle tone between shadow and base
        self.blur = blur            # soften the whole figure (painterly)
        self.eye = eye
        self.build = build          # limb thickness
        self.hatch = hatch          # ink hatching in the shadows (manga)


STYLES = {
    "storybook": Style("storybook", 1.0, 0.95, None, 0.4, 0.16, False, 0, "big", 1.08),
    "ink": Style("ink", 0.8, 1.0, (40, 30, 30), 0.5, 0.0, False, 0, "line", 0.92),
    "oil": Style("oil", 0.86, 0.0, None, 0.46, 0.26, True, 1, "real", 0.96),
    "manga": Style("manga", 0.74, 1.1, (22, 16, 20), 0.52, 0.07, False, 0, "manga", 0.88, hatch=True),
}


def current():
    return STYLES.get(STYLE[0])


def cycle():
    i = ORDER.index(STYLE[0]) if STYLE[0] in ORDER else 0
    STYLE[0] = ORDER[(i + 1) % len(ORDER)]
    return STYLE[0]


# ====================================================================== shading any closed shape
def _normals(pts):
    n = len(pts)
    area = 0.0
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        area += x0 * y1 - x1 * y0
    sgn = 1.0 if area > 0 else -1.0
    out = []
    for i in range(n):
        x0, y0 = pts[i - 1]
        x1, y1 = pts[(i + 1) % n]
        dx, dy = x1 - x0, y1 - y0
        d = math.hypot(dx, dy) or 1.0
        out.append((dy / d * sgn, -dx / d * sgn))       # outward
    return out


def shape(surf, pts, col, st, S, depth, flat=False, hatch=True):
    """Fill a closed outline with shading from the upper left.
    depth: the shape's local half-width in pixels (how deep the shadow can reach)."""
    if len(pts) < 3:
        return
    if flat:
        pygame.draw.polygon(surf, col, pts)
        return
    ns = _normals(pts)
    lit = [nx * LIGHT[0] + ny * LIGHT[1] for nx, ny in ns]      # +1 faces the light
    D = depth * st.shadow * 2.0
    R = depth * st.rim * 2.0
    if st.name == "ink":
        sh_col = mix(shade(col, 0.72), (40, 46, 90), 0.18)
    elif st.name == "manga":
        sh_col = mix(shade(col, 0.6), (30, 34, 74), 0.24)
    else:
        sh_col = warm(col, -0.28)
    rim_col = mix(warm(col, 0.28), (255, 238, 205), 0.25 if st.name == "oil" else 0.1)
    if st.name == "manga":
        rim_col = mix(col, (255, 255, 255), 0.55)
    pygame.draw.polygon(surf, sh_col, pts)
    if st.two_tone:
        mid = [(x - nx * D * max(0.0, -l) * 0.55, y - ny * D * max(0.0, -l) * 0.55)
               for (x, y), (nx, ny), l in zip(pts, ns, lit)]
        pygame.draw.polygon(surf, mix(sh_col, col, 0.5), mid)
    if R > 0:
        inner = [(x - nx * D * max(0.0, -l - 0.05), y - ny * D * max(0.0, -l - 0.05))
                 for (x, y), (nx, ny), l in zip(pts, ns, lit)]
        pygame.draw.polygon(surf, rim_col, inner)
    base = [(x - nx * (D * max(0.0, -l - 0.05) + R * max(0.0, l - 0.2)),
             y - ny * (D * max(0.0, -l - 0.05) + R * max(0.0, l - 0.2))) for (x, y), (nx, ny), l in zip(pts, ns, lit)]
    pygame.draw.polygon(surf, col, base)
    if st.outline:
        oc = st.ink if st.ink is not None else shade(col, 0.42)
        lw = max(1, int(round(st.outline * S)))
        pygame.draw.polygon(surf, oc, pts, lw)
        if st.hatch and hatch and D > 3:
            # parallel hatching strokes reaching in from the shadowed edge
            hl = max(1, int(S * 0.35))
            for i in range(0, len(pts), 2):
                l = lit[i]
                if l < -0.45:
                    nx, ny = ns[i]
                    ln = D * (0.5 + 0.6 * (-l - 0.45))
                    x, y = pts[i]
                    pygame.draw.line(surf, oc, (x, y), (x - nx * ln + LIGHT[0] * ln * 0.3, y - ny * ln + LIGHT[1] * ln * 0.3), hl)
        if st.ink is not None:
            # ink is heavier on the shadow side: one stroke per run of shadowed outline
            run = []
            for i in range(len(pts) + 1):
                j = i % len(pts)
                if lit[j] < -0.35:
                    run.append(pts[j])
                else:
                    if len(run) > 1:
                        pygame.draw.lines(surf, oc, False, run, lw + 1)
                    run = []
            if len(run) > 1:
                pygame.draw.lines(surf, oc, False, run, lw + 1)
    elif st.name == "oil":
        # no outline: just a soft dark edge where the form turns away
        for i in range(len(pts)):
            if lit[i] < -0.3:
                pygame.draw.line(surf, shade(sh_col, 0.82), pts[i], pts[(i + 1) % len(pts)], max(1, int(S * 0.4)))


# ====================================================================== anatomical outlines
# profiles: (t along the bone, half-width toward the front, half-width toward the back), in skeleton units
THIGH = ((0.0, 2.9, 3.0), (0.25, 3.25, 2.9), (0.7, 2.5, 2.3), (1.0, 2.0, 2.0))
SHIN = ((0.0, 2.0, 2.0), (0.3, 1.9, 2.6), (0.72, 1.35, 1.5), (1.0, 1.15, 1.25))
BOOT = ((0.0, 1.55, 1.7), (0.5, 1.4, 1.5), (1.0, 1.35, 1.45))
UARM = ((0.0, 2.3, 2.6), (0.3, 2.2, 2.25), (0.8, 1.75, 1.85), (1.0, 1.65, 1.65))
FARM = ((0.0, 1.75, 1.75), (0.22, 2.0, 1.95), (0.85, 1.2, 1.15), (1.0, 1.1, 1.05))
SLEEVE = ((0.0, 2.6, 2.9), (0.45, 2.5, 2.6), (1.0, 2.15, 2.3))
NECK = ((0.0, 1.9, 1.9), (1.0, 1.45, 1.6))


def limb_outline(a, b, prof, f, S, k=1.0, t0=0.0, t1=1.0, cap_a=True, cap_b=True):
    dx, dy = b[0] - a[0], b[1] - a[1]
    d = math.hypot(dx, dy) or 1.0
    ux, uy = dx / d, dy / d
    fx, fy = uy * f, -ux * f                           # toward the front of the limb
    pts = list(prof)

    def at(t):
        for i in range(len(pts) - 1):
            ta, wa, ba = pts[i]
            tb, wb, bb = pts[i + 1]
            if ta <= t <= tb:
                u = (t - ta) / max(1e-6, tb - ta)
                u = u * u * (3 - 2 * u)
                return wa + (wb - wa) * u, ba + (bb - ba) * u
        return pts[-1][1], pts[-1][2]
    lod = S < 3.5                                       # game size: fewer points are enough
    n = 4 if lod else 7
    ts = [t0 + (t1 - t0) * i / n for i in range(n + 1)]
    front, back = [], []
    for t in ts:
        wf, wb = at(t)
        cx, cy = a[0] + dx * t, a[1] + dy * t
        front.append((cx + fx * wf * S * k, cy + fy * wf * S * k))
        back.append((cx - fx * wb * S * k, cy - fy * wb * S * k))
    out = front[:]
    # rounded end at b: from the front edge around to the back edge
    wf, wb = at(t1)
    ex, ey = a[0] + dx * t1, a[1] + dy * t1
    if cap_b:
        r = (wf + wb) / 2 * S * k
        nc = 3 if lod else 6
        for i in range(1, nc):
            ang = math.pi * i / nc
            # rotate the front normal toward the back, bulging along the bone
            vx = fx * math.cos(ang) + ux * math.sin(ang)
            vy = fy * math.cos(ang) + uy * math.sin(ang)
            out.append((ex + vx * r, ey + vy * r))
    out += back[::-1]
    if cap_a:
        wf, wb = at(t0)
        sx, sy = a[0] + dx * t0, a[1] + dy * t0
        r = (wf + wb) / 2 * S * k
        nc = 3 if lod else 6
        for i in range(1, nc):
            ang = math.pi * i / nc
            vx = -fx * math.cos(ang) - ux * math.sin(ang)
            vy = -fy * math.cos(ang) - uy * math.sin(ang)
            out.append((sx + vx * r, sy + vy * r))
    return out


def limb(surf, a, b, prof, col, f, S, st, k=1.0, **kw):
    pts = limb_outline(a, b, prof, f, S, k * st.build, **kw)
    w = sum(p[1] + p[2] for p in prof) / (2 * len(prof)) * S * k * st.build
    shape(surf, pts, col, st, S, w)


def torso_outline(Tt, tl, hem, robe, S, st):
    """Profile of a body in a tunic: nape, upper back, small of the back, seat, hem; throat, chest, belly."""
    flare = 6.6 if robe else 5.9
    chest = 5.0 if st.name not in ("ink", "manga") else 5.3
    back = -4.7 if st.name not in ("ink", "manga") else -5.0
    waist_f, waist_b = 3.9, back + 0.8
    if st.name == "manga":
        # a heroic V: broad shoulders, a narrow waist, a short tunic that shows long legs
        back, chest = -5.4, 5.5
        waist_f, waist_b = 3.4, -3.9
        if not robe:
            hem, flare = 4.6, 5.2
    ctrl = [(-2.2, -tl - 0.9), (back + 0.4, -tl * 0.86), (back, -tl * 0.55), (waist_b, -tl * 0.2),
            (-4.6 if st.name == "manga" else -4.8, 0.4), (-flare * 0.92, hem * 0.55), (-flare, hem), (0.0, hem + 0.7),
            (flare * 0.96, hem), (flare * 0.82, hem * 0.45), (4.2 if st.name == "manga" else 4.4, 0.2),
            (waist_f, -tl * 0.2), (chest, -tl * 0.55), (chest - 0.5, -tl * 0.8), (1.9, -tl - 0.7)]
    from .quadruped import smooth_closed
    return [Tt(x * S, y * S) for x, y in smooth_closed(ctrl, 2 if S < 3.5 else 3)]


MANGA_HEAD = [(0.2, -5.4), (2.6, -4.8), (3.9, -3.1), (4.15, -1.5), (3.95, -0.8), (4.5, 0.3), (5.1, 1.0),
              (4.4, 1.35), (4.45, 2.1), (4.15, 2.6), (4.15, 3.3), (3.2, 4.55), (1.2, 4.2), (-0.3, 2.9),
              (-2.2, 2.5), (-4.0, 1.2), (-4.7, -1.1), (-3.7, -4.0)]


def head_outline(T, r, st=None):
    """The head in profile: crown, forehead, brow, nose, lips, chin, jaw, back of the skull."""
    if st is not None and st.name == "manga":
        from .quadruped import smooth_closed
        return [T(x * r, y * r) for x, y in (MANGA_HEAD if r < 3.0 else smooth_closed(MANGA_HEAD, 2))]
    ctrl = [(0.2, -5.3), (2.7, -4.7), (4.0, -3.0), (4.25, -1.5), (4.0, -0.85), (4.6, 0.2), (5.35, 1.15),
            (4.45, 1.45), (4.55, 2.25), (4.25, 2.75), (4.4, 3.45), (3.6, 4.55), (1.4, 4.7), (-0.4, 3.4),
            (-2.2, 2.6), (-4.0, 1.3), (-4.7, -1.0), (-3.7, -3.9)]
    from .quadruped import smooth_closed
    return [T(x * r, y * r) for x, y in (ctrl if r < 3.0 else smooth_closed(ctrl, 2))]


def hand(surf, c, f, S, col, st, wrist=None):
    """A mitten hand: the palm continues the forearm, fingers curl, a thumb points forward."""
    r = 1.3 * S * st.build
    if wrist is not None:
        dx, dy = c[0] - wrist[0], c[1] - wrist[1]
        d = math.hypot(dx, dy) or 1.0
        ux, uy = dx / d, dy / d
    else:
        ux, uy = 0.0, 1.0
    px, py = -uy, ux
    pts = []
    for i in range(14):
        a = i / 14 * math.tau
        rr = r * (1.25 if math.cos(a) > 0 else 1.0)          # longer toward the fingertips
        lx, ly = math.cos(a) * rr, math.sin(a) * r * 0.9
        pts.append((c[0] + ux * lx + px * ly, c[1] + uy * lx + py * ly))
    shape(surf, pts, col, st, S, r)
    tx, ty = c[0] + f * r * 0.8 - ux * r * 0.2, c[1] - r * 0.3
    pygame.draw.circle(surf, warm(col, -0.1), (tx, ty), r * 0.42)


def shoe(surf, knee, foot, f, col, st, S):
    x, y = foot
    ctrl = [(-2.4, -3.2), (0.8, -3.0), (2.4, -1.6), (4.6, -0.5), (4.9, 0.4), (2.0, 0.7), (-2.6, 0.6), (-2.9, -0.6)]
    from .quadruped import smooth_closed
    pts = [(x + px * S * f, y + py * S) for px, py in smooth_closed(ctrl, 2)]
    shape(surf, pts, col, st, S, 1.6 * S)
    pygame.draw.line(surf, shade(col, 0.55), (x - 2.6 * S * f, y + 0.5 * S), (x + 4.4 * S * f, y + 0.5 * S),
                     max(1, int(S * 0.6)))


# ====================================================================== the figure
def draw_humanoid_styled(surf, h, sx, sy, scale, tint, ss, st):
    from . import rig as R
    f = h.facing
    L = h.look
    R._EDGE[0] = 0.55 * scale
    rd = getattr(h, "ragdoll", None)
    p = h.pose
    if rd is not None and rd.points:
        J = {k: (sx + (v[0] - h.cx) * ss, sy + (v[1] - h.feet) * ss) for k, v in rd.points.items()}
    else:
        J = R.place(R.skeleton(p), sx, sy, f, p.rot, scale)
    hip, sh, head = J["hip"], J["sh"], J["head"]
    ux, uy = sh[0] - hip[0], sh[1] - hip[1]
    ul = math.hypot(ux, uy) or 1.0
    ux, uy = ux / ul, uy / ul
    fwd = (-uy * f, ux * f)
    down = (-ux, -uy)
    S = scale
    skin, tunic, hose = L["skin"], L["tunic"], L["hose"]
    boots = L.get("boots", (60, 44, 32))
    armor = h.armor
    plated = armor is not None and armor.style in ("mail", "plate")
    body_c = armor.color if plated else tunic
    if tint:
        skin = tunic = hose = boots = body_c = tint
    inj = getattr(h, "injury", None) or {}
    wd = h.weapon_def
    flat = bool(tint)
    if flat:
        st = STYLES["storybook"]

    def lim(a, b, prof, col, **kw):
        if flat:
            pygame.draw.polygon(surf, col, limb_outline(a, b, prof, f, S, st.build, **kw))
        else:
            limb(surf, a, b, prof, col, f, S, st, **kw)
    back = 0.72
    # -------------------------------------------------- back layer
    if wd is not None and p.weapon_mode == "sheathed" and wd.key != "fists" and not tint:
        Tb = R.frame(hip, fwd, down)
        R._draw_weapon(surf, wd, Tb(-3 * S, -2 * S), Tb(-3 * S - wd.length * 0.45 * S, 8 * S), f, S, sheathed=True)
    sleeve_c = body_c if plated else tunic
    lim(J["sh"], J["eb"], SLEEVE if not plated else UARM, shade(sleeve_c, back))
    lim(J["eb"], J["hb"], FARM, shade(body_c if plated else skin, back))
    if not flat:
        hand(surf, J["hb"], f, S, shade(skin, back), st, J["eb"])
    lim(hip, J["kb"], THIGH, shade(hose, back))
    lim(J["kb"], J["fb"], SHIN, shade(hose, back))
    lim(J["kb"], J["fb"], BOOT, shade(boots, back), t0=0.5, cap_a=False)
    if not flat:
        shoe(surf, J["kb"], J["fb"], f, shade(boots, back), st, S)
    if h.shield is not None and not p.shield_up and not tint:
        if getattr(h, "mount", None) is not None:
            R._draw_shield(surf, h, (hip[0] - f * 11 * S, hip[1] + 10 * S), f, S * 0.9, raised=False)
            pygame.draw.line(surf, (70, 46, 28), (hip[0] - f * 6 * S, hip[1] + 1 * S),
                             (hip[0] - f * 11 * S, hip[1] + 5 * S), max(1, int(S * 0.6)))
        else:
            R._draw_shield(surf, h, J["hb"], f, S, raised=False)
    # -------------------------------------------------- torso
    Tt = R.frame(hip, fwd, down)
    if st.name == "manga" and not flat and not L.get("robe"):
        sc_ = L.get("trim") or (L.get("tabard") or (None,))[0] or (176, 40, 38)
        sash(surf, h, Tt, S, st, sc_)
    tl = ul / S
    robe = L.get("robe", False)
    hem = 17 if robe else 6.0
    hw = 6.4 if robe else 5.8
    tpts = torso_outline(Tt, tl, hem, robe, S, st)
    if flat:
        pygame.draw.polygon(surf, body_c, tpts)
    else:
        shape(surf, tpts, body_c, st, S, 4.8 * S)

        def shaper(pts, c, k=0.9):
            shape(surf, [Tt(x, y) for x, y in pts], c, st, S, 3.0 * S)
        R.torso_details(surf, Tt, L, armor, plated, body_c, tl, hem, hw, S, inj, shaper)
    # -------------------------------------------------- front leg
    lim(hip, J["kf"], THIGH, hose)
    lim(J["kf"], J["ff"], SHIN, hose)
    lim(J["kf"], J["ff"], BOOT, boots, t0=0.5, cap_a=False)
    if not flat:
        shoe(surf, J["kf"], J["ff"], f, boots, st, S)
        if st.name == "ink":
            # a knee crease
            k_ = J["kf"]
            pygame.draw.line(surf, st.ink, (k_[0] - f * S, k_[1] - S * 0.5), (k_[0] + f * S * 0.8, k_[1] + S * 0.6),
                             max(1, int(S * 0.5)))
    if inj.get("legs", 0) >= 1 and not tint:
        pygame.draw.circle(surf, (130, 20, 20), J["kf"], (1 + inj["legs"]) * S * 0.7)
    # -------------------------------------------------- neck and head
    hu = (head[0] - sh[0], head[1] - sh[1])
    hl = math.hypot(*hu) or 1.0
    hdown = (-hu[0] / hl, -hu[1] / hl)
    hfwd = (f * hdown[1], -f * hdown[0])
    hs = st.head
    k_neck = (2.5 + R.HEAD_R * hs) / (2.5 + R.HEAD_R)
    hc = (sh[0] + hu[0] * k_neck, sh[1] + hu[1] * k_neck)
    Th = R.frame(hc, hfwd, hdown)
    lim(sh, (hc[0] - hu[0] * 0.25, hc[1] - hu[1] * 0.25), NECK, shade(skin, 0.92), cap_a=False)
    draw_head(surf, h, Th, S * hs, st, tint, flat)
    # -------------------------------------------------- front arm, weapon, hand, shield
    lim(J["sh"], J["ef"], SLEEVE if not plated else UARM, sleeve_c)
    lim(J["ef"], J["hf"], FARM, body_c if plated else skin)
    if not plated and not flat:
        # the sleeve ends a little below the elbow: a soft cuff in the sleeve's own colour
        cuff = limb_outline(J["ef"], J["hf"], ((0.0, 2.2, 2.2), (1.0, 2.0, 2.0)), f, S, st.build, t0=0.0, t1=0.3)
        pygame.draw.polygon(surf, sleeve_c, cuff)
        pygame.draw.lines(surf, shade(sleeve_c, 0.55) if st.ink is None else st.ink, False, cuff[7:14],
                          max(1, int(S * 0.5)))
    if inj.get("arm_w", 0) >= 1 and not tint:
        pygame.draw.circle(surf, (130, 20, 20), J["ef"], (1 + inj["arm_w"]) * S * 0.7)
    R.held_weapon(surf, h, J, p, wd, S, f, sx, sy, ss, rd, tint)
    if not flat:
        hand(surf, J["hf"], f, S, skin, st, J["ef"])
    if p.shield_up and h.shield is not None and not tint:
        hfp = J["hf"]
        R._draw_shield(surf, h, (hfp[0] + 2 * f * S, hfp[1] - 3 * S), f, S, raised=True)
    if h.hurt_flash > 0:
        pygame.draw.circle(surf, (255, 255, 255), hc, R.HEAD_R * S * hs + S, max(1, int(S)))


def draw_head(surf, h, T, r, st, tint, flat):
    from . import rig as R
    L = h.look
    skin = L["skin"] if not tint else tint
    pts = head_outline(T, r, st)
    if flat:
        pygame.draw.polygon(surf, skin, pts)
        return
    shape(surf, pts, skin, st, r, 3.2 * r, hatch=False)
    ink = st.ink if st.ink is not None else shade(skin, 0.45)
    lw = max(1, int(r * 0.45))
    hair = L["hair"]
    # ear
    e = T(-0.6 * r, 0.6 * r)
    pygame.draw.ellipse(surf, warm(skin, -0.12), (e[0] - r * 0.9, e[1] - r * 1.3, r * 1.8, r * 2.6))
    pygame.draw.arc(surf, shade(skin, 0.6) if st.ink is None else ink,
                    (e[0] - r * 0.9, e[1] - r * 1.3, r * 1.8, r * 2.6), 0, math.tau, max(1, int(r * 0.3)))
    # eye
    ex, ey = 2.75, -0.55
    if st.eye == "big":
        c = T(ex * r, ey * r)
        pygame.draw.ellipse(surf, (246, 244, 238), (c[0] - r * 0.95, c[1] - r * 0.8, r * 1.9, r * 1.6))
        pc = T((ex + 0.35) * r, ey * r)
        pygame.draw.circle(surf, (36, 28, 24), pc, r * 0.6)
        pygame.draw.circle(surf, (255, 255, 255), T((ex + 0.5) * r, (ey - 0.3) * r), r * 0.2)
        pygame.draw.line(surf, shade(hair, 0.75), T(1.8 * r, -1.9 * r), T(3.9 * r, -1.7 * r), lw)
        pygame.draw.circle(surf, mix(skin, (220, 100, 96), 0.3), T(3.0 * r, 1.4 * r), r * 0.9)
        pygame.draw.arc(surf, shade(skin, 0.55), pygame.Rect(T(3.4 * r, 2.4 * r), (0, 0)).inflate(r * 1.4, r * 0.8),
                        math.pi, math.tau, max(1, int(r * 0.3)))
    elif st.eye == "manga":
        r0 = r
        r = r * 1.3
        ex, ey = ex / 1.3 + 0.05, ey / 1.3 - 0.1
        # a sharp, intense eye: heavy upper lid with a flick at the outer corner, a dark iris with a glint,
        # a short lower lid, and a brow that drives down toward the nose
        lid = [T((ex - 0.95) * r, (ey - 0.05) * r), T((ex - 0.2) * r, (ey - 0.45) * r), T((ex + 0.75) * r, (ey - 0.4) * r)]
        pygame.draw.polygon(surf, (250, 248, 244), [lid[0], lid[1], lid[2], T((ex + 0.5) * r, (ey + 0.35) * r),
                                                     T((ex - 0.5) * r, (ey + 0.3) * r)])
        pygame.draw.circle(surf, (40, 26, 22), T((ex + 0.25) * r, (ey - 0.05) * r), r * 0.42)
        pygame.draw.circle(surf, (255, 255, 255), T((ex + 0.35) * r, (ey - 0.2) * r), max(1.0, r * 0.14))
        pygame.draw.lines(surf, ink, False, lid, lw + 1)
        pygame.draw.line(surf, ink, lid[0], T((ex - 1.4) * r, (ey - 0.4) * r), lw)           # the flick
        pygame.draw.line(surf, ink, T((ex - 0.3) * r, (ey + 0.4) * r), T((ex + 0.45) * r, (ey + 0.36) * r),
                         max(1, lw - 1))
        r = r0
        brow = [T(1.3 * r, -2.2 * r), T(2.6 * r, -1.9 * r), T(4.1 * r, -1.2 * r), T(2.6 * r, -1.55 * r)]
        pygame.draw.polygon(surf, shade(hair, 0.5), brow)
        r = r0
        pygame.draw.line(surf, ink, T(4.95 * r, 1.0 * r), T(4.4 * r, 1.35 * r), max(1, lw - 1))     # nose tip
        pygame.draw.line(surf, ink, T(3.75 * r, 2.4 * r), T(4.35 * r, 2.35 * r), max(1, lw - 1))    # mouth
        pygame.draw.line(surf, mix(skin, (40, 40, 80), 0.3), T(1.2 * r, 4.1 * r), T(-0.2 * r, 2.9 * r), lw)
    elif st.eye == "line":
        a, b = T((ex - 0.7) * r, (ey + 0.1) * r), T((ex + 0.6) * r, (ey - 0.15) * r)
        pygame.draw.line(surf, ink, a, b, lw)
        pygame.draw.circle(surf, ink, T((ex + 0.2) * r, ey * r), r * 0.4)
        pygame.draw.line(surf, ink, T(1.7 * r, -1.6 * r), T(4.1 * r, -1.9 * r), lw + 1)          # brow
        pygame.draw.line(surf, ink, T(4.5 * r, 1.5 * r), T(3.7 * r, 2.1 * r), max(1, lw - 1))      # nostril line
        pygame.draw.line(surf, ink, T(4.0 * r, 2.55 * r), T(4.55 * r, 2.5 * r), max(1, lw - 1))    # lips
        pygame.draw.line(surf, ink, T(0.6 * r, 4.4 * r), T(-0.3 * r, 3.4 * r), lw)                  # jaw
    else:
        sock = T(ex * r, (ey + 0.1) * r)
        pygame.draw.ellipse(surf, warm(skin, -0.16), (sock[0] - r * 1.1, sock[1] - r * 0.8, r * 2.2, r * 1.6))
        c = T((ex + 0.2) * r, ey * r)
        pygame.draw.circle(surf, (40, 30, 26), c, r * 0.45)
        pygame.draw.circle(surf, (236, 232, 222), T((ex + 0.35) * r, (ey - 0.15) * r), r * 0.15)
        pygame.draw.line(surf, warm(hair, -0.1), T(1.9 * r, -1.75 * r), T(3.9 * r, -1.6 * r), lw)
        pygame.draw.line(surf, mix(skin, (170, 70, 70), 0.35), T(4.0 * r, 2.5 * r), T(4.5 * r, 2.45 * r), lw)
        pygame.draw.circle(surf, mix(skin, (220, 110, 100), 0.18), T(2.8 * r, 1.5 * r), r * 1.1)
    if L.get("beard"):
        bd = [(0.4 * r, 1.4 * r), (2.6 * r, 2.4 * r), (4.4 * r, 2.4 * r), (4.7 * r, 3.6 * r), (3.6 * r, 5.6 * r),
              (1.0 * r, 5.4 * r), (-0.8 * r, 3.2 * r)]
        shape(surf, [T(x, y) for x, y in bd], hair, st, r, 1.6 * r)
        for k in range(4):
            pygame.draw.line(surf, warm(hair, 0.22), T((1.0 + k) * r, 3.0 * r), T((0.8 + k) * r, 5.0 * r),
                             max(1, int(r * 0.3)))
    hel = h.helmet
    if st.name == "manga" and not hel and L.get("hat") in (None, "", "tonsure", "crown", "coronet", "cap"):
        manga_hair(surf, h, T, r, st, hair, L)
        R._hat(surf, T, r, L)
        return
    if hel:
        R._helmet(surf, T, r, R.HELMETS[hel][1], L)
    else:
        hp = [(-4.9, 2.6), (-5.2, -1.0), (-4.0, -4.4), (-1.4, -5.9), (1.8, -5.7), (4.0, -3.9), (4.5, -2.5),
              (2.4, -3.1), (0.4, -2.9), (-1.4, -1.5), (-2.4, 0.8), (-3.0, 3.0)]
        shape(surf, [T(x * r, y * r) for x, y in hp], hair, st, r, 2.0 * r)
        for k in range(5):
            a = T((-3.4 + k * 1.3) * r, (-4.8 + abs(k - 2) * 0.4) * r)
            b = T((-4.4 + k * 1.15) * r, (-1.9 + k * 0.2) * r)
            pygame.draw.line(surf, warm(hair, 0.22) if st.name != "ink" else shade(hair, 0.6), a, b,
                             max(1, int(r * 0.35)))
        R._hat(surf, T, r, L)


def manga_hair(surf, h, T, r, st, hair, L):
    """Spiky hair swept back by the wind, a bright band where the light rings it, bangs over the brow;
    some wear it long and tied, the tail streaming behind them."""
    seed = sum(L["hair"]) + sum(L["skin"]) * 3
    vx = abs(getattr(h, "vx", 0.0))
    t = getattr(h, "anim_t", 0.0)
    sweep = 0.25 + min(0.6, vx / 300.0)                 # the faster, the further back
    pts = []
    n = 7
    for i in range(n + 1):
        # around the skull from the brow (front-top) over the crown to the nape
        a = -0.3 * math.pi - (0.95 * math.pi) * i / n       # 0 = forward, -pi/2 = up, -pi = back
        ca, sa = math.cos(a), math.sin(a)
        base = 5.05
        pts.append((ca * base, sa * base * 1.04))
        if 0 < i < n:
            m = a - 0.95 * math.pi / n * 0.5
            ln = 1.8 + 2.4 * ((seed * (i + 3)) % 7) / 7.0
            ex, ey = math.cos(m) * (base + ln), math.sin(m) * (base + ln)
            ex -= sweep * ln * 1.3                          # swept back
            ey += sweep * ln * 0.3 + math.sin(t * 6 + i) * 0.15 * vx / 200
            pts.append((ex, ey))
    # down the back of the neck, then forward above the ear to the temple
    pts += [(-4.9, 1.6), (-4.6, 3.2), (-3.4, 2.4), (-2.4, 0.4), (-1.2, -1.6), (0.8, -2.4)]
    # bangs falling over the brow
    pts += [(1.9, -1.4), (2.5, -2.7), (3.3, -1.6), (3.9, -3.0), (4.5, -2.4), (4.4, -3.9)]
    W = [T(x * r, y * r) for x, y in pts]
    if (seed % 3) == 0:
        # a tied tail streaming behind
        root = (-3.6, -3.4)
        tail = [root]
        for k in range(1, 7):
            u = k / 6
            tail.append((root[0] - u * (5.5 + 5 * sweep), root[1] + u * (3.5 - 2.5 * sweep) + math.sin(t * 5 - u * 3) * u * 0.9))
        left = [(x, y - (1.0 - k / 6) * 1.1) for k, (x, y) in enumerate(tail)]
        right = [(x, y + (1.0 - k / 6) * 1.1) for k, (x, y) in enumerate(tail)]
        tw = [T(x * r, y * r) for x, y in left + right[::-1]]
        shape(surf, tw, hair, st, r, 1.0 * r)
        tie = T(root[0] * r, root[1] * r)
        pygame.draw.circle(surf, L.get("trim") or (170, 40, 36), tie, r * 0.55)
    shape(surf, W, hair, st, r, 2.2 * r, hatch=False)
    # the ring of light on the hair
    band = [T(math.cos(a) * 4.2 * r - 0.3 * r, math.sin(a) * 4.3 * r) for a in
            [-0.45 * math.pi - 0.08 * k for k in range(8)]]
    pygame.draw.lines(surf, mix(hair, (255, 255, 255), 0.45), False, band, max(1, int(r * 0.45)))


def sash(surf, h, Tt, S, st, color):
    """A sash knotted at the waist, its two ends streaming out behind."""
    vx = abs(getattr(h, "vx", 0.0))
    t = getattr(h, "anim_t", 0.0)
    lift = min(1.0, vx / 240.0)
    for j, (ln, ph) in enumerate(((14.0, 0.0), (10.5, 1.7))):
        pts_l, pts_r = [], []
        for k in range(7):
            u = k / 6
            x = -4.6 - u * ln * (0.55 + 0.45 * lift)
            y = 0.2 + u * ln * (0.85 - 0.75 * lift) + math.sin(t * 6 + ph - u * 4) * u * (0.6 + 1.4 * lift)
            w = 1.4 * (1 - u * 0.45)
            pts_l.append((x, y - w))
            pts_r.append((x, y + w))
        W = [Tt(x * S, y * S) for x, y in pts_l + pts_r[::-1]]
        shape(surf, W, shade(color, 1.0 - 0.12 * j), st, S, 0.9 * S)
