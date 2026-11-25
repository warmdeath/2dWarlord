"""Fonts, panels and the bilingual text renderer."""
import pygame

from ..settings import GERMAN_COLOR, GLOSS_COLOR, PARCHMENT, INK, GOLD
from ..society.dialogue import parse

_fonts = {}


def font(size, bold=False, serif=True):
    key = (size, bold, serif)
    f = _fonts.get(key)
    if f is None:
        names = "georgia,palatinolinotype,bookantiqua,dejavuserif,liberationserif,serif" if serif else \
            "segoeui,dejavusans,liberationsans,arial"
        try:
            f = pygame.font.SysFont(names, size, bold=bold)
        except Exception:
            f = pygame.font.Font(None, size + 4)
        _fonts[key] = f
    return f


def text(surf, s, pos, size=16, color=(235, 230, 220), bold=False, center=False, shadow=True, right=False):
    f = font(size, bold)
    img = f.render(s, True, color)
    x, y = pos
    if center:
        x -= img.get_width() // 2
    if right:
        x -= img.get_width()
    if shadow:
        sh = f.render(s, True, (0, 0, 0))
        surf.blit(sh, (x + 1, y + 1))
    surf.blit(img, (x, y))
    return img.get_width()


def panel(surf, rect, alpha=215, color=(28, 24, 22), border=GOLD, radius=6):
    r = pygame.Rect(rect)
    s = pygame.Surface(r.size, pygame.SRCALPHA)
    pygame.draw.rect(s, (*color, alpha), s.get_rect(), border_radius=radius)
    surf.blit(s, r.topleft)
    if border:
        pygame.draw.rect(surf, border, r, 1, border_radius=radius)
    return r


def parchment(surf, rect):
    r = pygame.Rect(rect)
    pygame.draw.rect(surf, PARCHMENT, r, border_radius=4)
    pygame.draw.rect(surf, (150, 120, 80), r, 2, border_radius=4)
    pygame.draw.rect(surf, (196, 176, 136), r.inflate(-8, -8), 1, border_radius=3)
    return r


def bilingual(surf, line, pos, size=16, width=600, base=(236, 232, 222), german=GERMAN_COLOR, gloss=True,
              center=False, dark=False):
    """Render a [Deutsch|english] marked line with wrapping. Returns height used."""
    segs, gl = parse(line)
    f = font(size)
    fb = font(size, bold=True)
    words = []
    for s, is_de in segs:
        parts = s.split(" ")
        for i, p in enumerate(parts):
            if p == "" and i > 0:
                continue
            words.append((p, is_de, i < len(parts) - 1))
    lines = [[]]
    x = 0
    space = f.size(" ")[0]
    for wtxt, is_de, trailing in words:
        ff = fb if is_de else f
        ww = ff.size(wtxt)[0]
        if x + ww > width and lines[-1]:
            lines.append([])
            x = 0
        lines[-1].append((wtxt, is_de, ww, trailing))
        x += ww + (space if trailing else 0)
    y = pos[1]
    lh = f.get_linesize()
    if dark:
        base = INK
        german = (150, 60, 20)
    for ln in lines:
        total = sum(w + (space if t else 0) for _, _, w, t in ln)
        x = pos[0] - (total // 2 if center else 0)
        for wtxt, is_de, ww, trailing in ln:
            ff = fb if is_de else f
            if not dark:
                surf.blit(ff.render(wtxt, True, (0, 0, 0)), (x + 1, y + 1))
            surf.blit(ff.render(wtxt, True, german if is_de else base), (x, y))
            x += ww + (space if trailing else 0)
        y += lh
    if gloss and gl:
        g = "  ·  ".join(f"{de} = {en}" for de, en in dict(gl).items())
        gf = font(max(11, size - 4))
        gx = pos[0] - (gf.size(g)[0] // 2 if center else 0)
        col = GLOSS_COLOR if not dark else (90, 70, 50)
        if gf.size(g)[0] > width + 200:
            g = g[: int(len(g) * (width + 200) / gf.size(g)[0]) - 2] + "…"
        if not dark:
            surf.blit(gf.render(g, True, (0, 0, 0)), (gx + 1, y + 2))
        surf.blit(gf.render(g, True, col), (gx, y + 1))
        y += gf.get_linesize() + 2
    return y - pos[1]


def bar(surf, x, y, w, h, frac, color, back=(40, 34, 30)):
    pygame.draw.rect(surf, back, (x, y, w, h), border_radius=2)
    pygame.draw.rect(surf, color, (x, y, int(w * max(0.0, min(1.0, frac))), h), border_radius=2)
    pygame.draw.rect(surf, (0, 0, 0), (x, y, w, h), 1, border_radius=2)


def item_icon(surf, key, rect):
    from ..items.items import ITEMS
    d = ITEMS.get(key)
    r = pygame.Rect(rect)
    if d is None:
        return
    c = d.color
    cx, cy = r.center
    ic = d.icon
    if ic == "block":
        pygame.draw.rect(surf, c, r.inflate(-12, -12), border_radius=2)
        pygame.draw.rect(surf, (0, 0, 0), r.inflate(-12, -12), 1, border_radius=2)
    elif ic in ("sword", "longsword", "dagger"):
        pygame.draw.line(surf, (220, 224, 232), (r.left + 8, r.bottom - 8), (r.right - 6, r.top + 6), 3)
        pygame.draw.line(surf, (190, 160, 70), (r.left + 8, r.bottom - 14), (r.left + 14, r.bottom - 8), 3)
    elif ic in ("spear", "pike", "lance", "fork", "halberd"):
        pygame.draw.line(surf, (120, 86, 52), (r.left + 6, r.bottom - 6), (r.right - 8, r.top + 8), 2)
        pygame.draw.polygon(surf, (220, 224, 232), [(r.right - 4, r.top + 4), (r.right - 12, r.top + 8),
                                                    (r.right - 8, r.top + 12)])
    elif ic in ("axe", "pick", "hammer", "mace", "club", "sickle", "flail"):
        pygame.draw.line(surf, (120, 86, 52), (r.left + 8, r.bottom - 6), (r.right - 10, r.top + 8), 3)
        pygame.draw.circle(surf, (200, 204, 212), (r.right - 10, r.top + 9), 5)
    elif ic == "bow":
        pygame.draw.arc(surf, (140, 100, 60), r.inflate(-10, -6), -1.3, 1.3, 3)
        pygame.draw.line(surf, (230, 230, 220), (cx + 6, r.top + 6), (cx + 6, r.bottom - 6), 1)
    elif ic == "crossbow":
        pygame.draw.line(surf, (120, 86, 52), (r.left + 6, cy), (r.right - 6, cy), 4)
        pygame.draw.line(surf, (90, 90, 96), (r.right - 10, r.top + 8), (r.right - 10, r.bottom - 8), 2)
    elif ic == "shield":
        pygame.draw.polygon(surf, c, [(r.left + 8, r.top + 7), (r.right - 8, r.top + 7), (r.right - 8, cy),
                                      (cx, r.bottom - 5), (r.left + 8, cy)])
    elif ic == "armor":
        pygame.draw.rect(surf, c, (r.left + 9, r.top + 7, r.w - 18, r.h - 12), border_radius=3)
    elif ic == "helmet":
        pygame.draw.circle(surf, c, (cx, cy + 3), 9, draw_top_left=True, draw_top_right=True)
    elif ic == "coin":
        pygame.draw.circle(surf, c, (cx, cy), 7)
    elif ic == "torch":
        pygame.draw.line(surf, (120, 86, 52), (cx, r.bottom - 6), (cx, cy - 2), 3)
        pygame.draw.circle(surf, (255, 180, 60), (cx, cy - 6), 5)
    elif ic == "arrow":
        pygame.draw.line(surf, (200, 190, 170), (r.left + 6, r.bottom - 6), (r.right - 6, r.top + 6), 2)
    elif ic in ("boat", "horse"):
        pygame.draw.ellipse(surf, c, r.inflate(-8, -16))
    else:
        pygame.draw.circle(surf, c, (cx, cy), 8)
        pygame.draw.circle(surf, (0, 0, 0), (cx, cy), 8, 1)
