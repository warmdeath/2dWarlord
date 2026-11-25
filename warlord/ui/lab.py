"""Die Werkstatt: shaping at a workbench with the mouse, slowly and exactly.

Put a piece of wood on the bench (a trunk you carried here, a log lying nearby, or wood from your bag) and
work it: the saw cuts straight through along the line you drag (Shift snaps to the guide), the chisel
carves away a groove, the drill makes holes, the rasp rounds the edges. On the right, every known shape
shows how close your piece is to it. "Fertig" takes what you made — with its exact outline and its quality.
"""
import math

import pygame
from shapely.geometry import Polygon

from ..settings import SCREEN_W, SCREEN_H, GOLD, GERMAN_COLOR
from ..items.items import ITEMS
from ..items import shaping as SH
from ..poly.objects import PhysObject, centroid
from .common import text, panel, ltext, bar

TOOLS = [("saege", "Säge", "saw"), ("beitel", "Beitel", "chisel"), ("bohrer", "Bohrer", "drill"),
         ("raspel", "Raspel", "rasp")]
BLANKS = {"wood": (64, 10), "beam": (128, 18), "planks": (112, 4), "log": (150, 14)}
BOARD = 4.0       # a board is 4 px thick (about a hand), the saw kerf and the bark are lost
BARK = 1.0
PER_PLANK = 48.0  # one 'Bretter' item per 48 px of board length


class Lab:
    def __init__(self, ui, bench):
        self.ui = ui
        self.g = ui.g
        self.bench = bench
        self.wp = None
        self.src = None          # ("bag", key) | ("object", PhysObject) | ("carried", PhysObject)
        self.tool = "saege"
        self.width = 8.0
        self.drag = None
        self.target = None
        self.rects = []
        self.msg = ""
        self.canvas = pygame.Rect(260, 110, 700, 430)
        self.scale = 3.0
        self.offset = (0, 0)
        self.cache = None

    # ------------------------------------------------------------------ material
    def sources(self):
        g = self.g
        p = g.player
        out = []
        if getattr(p, "carrying", None) is not None and p.carrying.mat in ("log", "plank", "timber"):
            out.append(("carried", p.carrying, "Stamm in den Armen (the log you carry)"))
        objs = sorted(g.world.objects, key=lambda o: (o.kind != "log", -len(o.pts)))
        from ..poly.objects import area
        for o in objs:
            if o.mat in ("log", "plank", "timber") and not o.anchored and abs(o.x - self.bench.x) < 140 and \
                    abs(o.y - self.bench.y) < 80 and o.crown is None and area(o.pts) > 240:
                nm = "Stamm" if o.kind == "log" else (ITEMS[o.item].de if o.item in ITEMS else "Rohling")
                out.append(("object", o, f"{nm} am Boden (lying by the bench)"))
        for k in ("beam", "wood", "planks"):
            if p.inv.count(k):
                out.append(("bag", k, f"{ITEMS[k].de} aus dem Rucksack ({p.inv.count(k)})"))
        return out

    def load(self, src):
        kind, ref, _ = src
        p = self.g.player
        if kind == "bag":
            p.inv.remove(ref, 1)
            w, h = BLANKS[ref]
            self.wp = SH.Workpiece.log(w, h)
        else:
            o = ref
            pts = [(x, y) for x, y in o.pts]
            self.wp = SH.Workpiece(Polygon(pts).buffer(0), o.mat)
            if kind == "carried":
                p.carrying = None
            else:
                o.remove()
        self.src = (kind, ref)
        self.fit()
        self.cache = None

    def fit(self):
        x0, y0, x1, y1 = self.wp.poly.bounds
        w, h = max(1, x1 - x0), max(1, y1 - y0)
        c = self.canvas
        self.scale = min((c.w - 60) / w, (c.h - 60) / h, 6.0)
        self.offset = (c.centerx - (x0 + w / 2) * self.scale, c.centery - (y0 + h / 2) * self.scale)

    def to_local(self, pos):
        return ((pos[0] - self.offset[0]) / self.scale, (pos[1] - self.offset[1]) / self.scale)

    def to_screen(self, pt):
        return (pt[0] * self.scale + self.offset[0], pt[1] * self.scale + self.offset[1])

    # ------------------------------------------------------------------ input
    def key(self, k):
        if k == pygame.K_z or k == pygame.K_BACKSPACE:
            if self.wp is not None and self.wp.undo():
                self.cache = None
        elif k in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
            self.tool = TOOLS[k - pygame.K_1][0]
        elif k == pygame.K_5:
            self.split()
        elif k == pygame.K_RETURN:
            self.finish()
        elif k == pygame.K_ESCAPE:
            self.cancel()

    def wheel(self, dy):
        self.width = max(3.0, min(20.0, self.width + dy))

    def snap(self, pt):
        if self.target is None or self.wp is None:
            return pt
        guide = self.wp.guide(self.target)
        best, bd = pt, 10 / self.scale
        for c in guide.exterior.coords:
            d = math.hypot(c[0] - pt[0], c[1] - pt[1])
            if d < bd:
                best, bd = c, d
        return best

    def mouse_down(self, pos, button):
        for rect, kind, val in self.rects:
            if rect.collidepoint(pos):
                self.button(kind, val)
                return
        if self.wp is None or not self.canvas.collidepoint(pos) or button != 1:
            return
        lp = self.to_local(pos)
        if self.tool == "bohrer":
            if self.wp.drill(lp, self.width / 2):
                self.g.sfx("dig")
                self.cache = None
            return
        if self.tool == "raspel":
            if self.wp.rasp():
                self.g.sfx("dig")
                self.cache = None
            return
        self.drag = [lp]

    def mouse_move(self, pos, buttons):
        if self.drag is not None and buttons[0]:
            lp = self.to_local(pos)
            if self.tool == "beitel":
                if math.hypot(lp[0] - self.drag[-1][0], lp[1] - self.drag[-1][1]) > 1.5:
                    self.drag.append(lp)
            else:
                if len(self.drag) == 1:
                    self.drag.append(lp)
                else:
                    self.drag[1] = lp

    def mouse_up(self, pos, button):
        if self.drag is None or self.wp is None:
            self.drag = None
            return
        mods = pygame.key.get_mods()
        if self.tool == "saege" and len(self.drag) >= 2:
            a, b = self.drag[0], self.drag[-1]
            if mods & pygame.KMOD_SHIFT:
                a, b = self.snap(a), self.snap(b)
            if self.wp.saw(a, b):
                self.g.sfx("chop")
                self.cache = None
        elif self.tool == "beitel" and len(self.drag) >= 1:
            if self.wp.carve(self.drag, self.width):
                self.g.sfx("dig")
                self.cache = None
        self.drag = None

    def button(self, kind, val):
        if kind == "tool":
            self.tool = val
        elif kind == "src":
            self.load(val)
        elif kind == "target":
            self.target = val
        elif kind == "undo":
            if self.wp is not None and self.wp.undo():
                self.cache = None
        elif kind == "finish":
            self.finish()
        elif kind == "split":
            self.split()
        elif kind == "cancel":
            self.cancel()

    # ------------------------------------------------------------------ splitting into boards
    def split_yield(self):
        """How many boards a straight piece gives when ripped lengthwise, and planks per board."""
        if self.wp is None:
            return 0, 0, 0.0
        p, L, _ = SH.normalise(self.wp.poly)
        x0, y0, x1, y1 = p.bounds
        T = y1 - y0
        # only the straight, solid part of the piece counts: how full is its bounding box?
        fill = self.wp.poly.area / max(1.0, L * T)
        if fill < 0.8:
            L *= fill
        boards = int((T - 2 * BARK) // BOARD)
        per = int(L // PER_PLANK)
        if boards < 1 or per < 1:
            return 0, 0, L
        return boards, per, L

    def split(self):
        n_b, per, L = self.split_yield()
        if not n_b:
            self.ui.toast("Too thin or too short to split into boards ([Bretter|planks]).", 3)
            return
        g = self.g
        p = g.player
        n = n_b * per
        left = p.inv.add("planks", n, quality=1.0)
        if left:
            g.drop_item("planks", left, self.bench.x, self.bench.y - 20)
        chips = max(1, int(L // 60))
        if p.inv.add("chip", chips):
            pass
        p.stats["shaped"] = p.stats.get("shaped", 0) + 1
        g.sfx("chop")
        g.emit("shaped", key="planks", q=1.0)
        self.ui.toast(f"[Gespalten|split]: {n} [Bretter|planks] ({n_b} boards), the bark and the saw dust "
                      f"go to the [Späne|chips].", 4)
        self.wp = None
        self.ui.modal = None

    # ------------------------------------------------------------------ results
    def _spawn(self, poly, kind, item, key, q, name=None):
        g = self.g
        pts = list(poly.exterior.coords)[:-1]
        cx, cy = centroid(pts)
        local = [(x - cx, y - cy) for x, y in pts]
        bx = self.bench.x + g.rng.uniform(-30, 30)
        by = self.bench.y - 30 - max(abs(y) for _, y in local)
        o = PhysObject.spawn(g.world, local, bx, by, "plank" if key in ("planks", "door", "sign_board") else
                             self.wp.mat if self.wp.mat in ("log", "plank", "timber") else "log", kind, item=item,
                             quality=q, shape_key=key, name=name)
        holes = [[(x - cx, y - cy) for x, y in h.coords] for h in poly.interiors]
        if holes:
            o.holes = holes
        return o

    def collect(self, poly, main=False):
        """Turn one finished piece into an item or an object. Returns a description."""
        g = self.g
        p = g.player
        key, q, _ = SH.identify(poly, lab=True)
        if key is None:
            if poly.area < 260:
                return None
            if poly.area < 900 or not main:
                if p.inv.add("wood", 1):
                    g.drop_item("wood", 1, self.bench.x, self.bench.y - 20)
                return "Holz"
            self._spawn(poly, "crafted", "wood", None, 0.0, name="Rohling")
            return "Rohling"
        item = SH.TEMPLATES[key][0]
        de = SH.TEMPLATES[key][1]
        if p.inv.bulky(item) or ITEMS[item].place == "object":
            self._spawn(poly, "crafted", item, item, q)
        else:
            left = p.inv.add(item, 1, quality=q)
            if left:
                g.drop_item(item, 1, self.bench.x, self.bench.y - 20, quality=q)
        p.stats["shaped"] = p.stats.get("shaped", 0) + 1
        g.emit("shaped", key=item, q=q)
        return f"{de} {int(q * 100)}%"

    def finish(self):
        if self.wp is None:
            self.ui.modal = None
            return
        made = [self.collect(self.wp.poly, main=True)]
        for off in self.wp.offcuts:
            made.append(self.collect(off))
        made = [m for m in made if m]
        self.ui.toast("[Fertig|done]: " + ", ".join(made), 4)
        self.wp = None
        self.ui.modal = None

    def cancel(self):
        if self.wp is not None:
            if self.wp.cuts == 0 and self.src and self.src[0] == "bag":
                self.g.player.inv.add(self.src[1], 1)
            else:
                self._spawn(self.wp.poly, "crafted" if self.wp.cuts else "log", "wood", None, 0.0,
                            name="Rohling" if self.wp.cuts else None)
        self.wp = None
        self.ui.modal = None

    # ------------------------------------------------------------------ drawing
    def draw(self, surf):
        r = panel(surf, (30, 30, SCREEN_W - 60, SCREEN_H - 60), 240)
        ltext(surf, "Werkstatt — the workbench", (r.x + 16, r.y + 10), 22, GOLD)
        text(surf, "1 Säge: drag a cut (Shift snaps to the guide) · 2 Beitel: carve (wheel = width) · 3 Bohrer · "
                   "4 Raspel · Z undo · Enter done · Esc stop", (r.x + 16, r.y + 42), 12, (190, 190, 180))
        self.rects = []
        mp = pygame.mouse.get_pos()
        c = self.canvas
        # the bench top
        pygame.draw.rect(surf, (120, 86, 54), c, border_radius=8)
        for i in range(c.y + 18, c.bottom, 26):
            pygame.draw.line(surf, (104, 74, 46), (c.x + 6, i), (c.right - 6, i), 2)
        pygame.draw.rect(surf, (70, 50, 32), c, 3, border_radius=8)
        if self.wp is None:
            text(surf, "Lay a piece of wood on the bench:", (r.x + 16, r.y + 80), 15, GERMAN_COLOR)
            srcs = self.sources()
            if not srcs:
                text(surf, "Nothing to work. Fell a tree and bring a [Stamm|log] (carry it with E), or bring "
                           "[Holz|wood].", (r.x + 16, r.y + 110), 13, (220, 200, 170))
            for i, s in enumerate(srcs[:8]):
                rect = pygame.Rect(r.x + 16, r.y + 110 + i * 30, 230, 26)
                hover = rect.collidepoint(mp)
                panel(surf, rect, 220 if hover else 180)
                text(surf, s[2], (rect.x + 8, rect.y + 5), 11, (240, 230, 210))
                self.rects.append((rect, "src", s))
            rect = pygame.Rect(r.x + 16, r.bottom - 50, 110, 30)
            panel(surf, rect, 200)
            text(surf, "Schließen", (rect.x + 14, rect.y + 7), 14)
            self.rects.append((rect, "cancel", None))
            return
        # the workpiece
        if self.cache is None:
            self.cache = self.wp.identify(lab=True)
        key, q, ranking = self.cache
        pts = [self.to_screen(p_) for p_ in self.wp.points()]
        if len(pts) >= 3:
            pygame.draw.polygon(surf, (196, 150, 98), pts)
            # grain lines clipped roughly to the shape
            pygame.draw.polygon(surf, (110, 76, 46), pts, 2)
            for h in self.wp.holes():
                hp = [self.to_screen(p_) for p_ in h]
                if len(hp) >= 3:
                    pygame.draw.polygon(surf, (120, 86, 54), hp)
                    pygame.draw.polygon(surf, (110, 76, 46), hp, 2)
        for off in self.wp.offcuts[-6:]:
            op = [self.to_screen(p_) for p_ in list(off.exterior.coords)]
            if len(op) >= 3:
                pygame.draw.polygon(surf, (150, 120, 84), op, 1)
        if self.target is not None:
            guide = self.wp.guide(self.target)
            gp = [self.to_screen(p_) for p_ in guide.exterior.coords]
            for i in range(len(gp) - 1):
                a, b = gp[i], gp[i + 1]
                L = math.hypot(b[0] - a[0], b[1] - a[1])
                n = max(1, int(L // 8))
                for k in range(0, n, 2):
                    f0, f1 = k / n, min(1.0, (k + 1) / n)
                    pygame.draw.line(surf, (255, 240, 170), (a[0] + (b[0] - a[0]) * f0, a[1] + (b[1] - a[1]) * f0),
                                     (a[0] + (b[0] - a[0]) * f1, a[1] + (b[1] - a[1]) * f1), 2)
            for hole in guide.interiors:
                hp = [self.to_screen(p_) for p_ in hole.coords]
                pygame.draw.lines(surf, (255, 240, 170), True, hp, 1)
        # the stroke being made
        if self.drag:
            sp = [self.to_screen(p_) for p_ in self.drag]
            if self.tool == "saege" and len(sp) >= 2:
                a, b = sp[0], sp[-1]
                dx, dy = b[0] - a[0], b[1] - a[1]
                L = math.hypot(dx, dy) or 1
                ext = 2000
                pygame.draw.line(surf, (255, 120, 80), (a[0] - dx / L * ext, a[1] - dy / L * ext),
                                 (a[0] + dx / L * ext, a[1] + dy / L * ext), 1)
                pygame.draw.line(surf, (255, 90, 60), a, b, 3)
            elif len(sp) >= 2:
                pygame.draw.lines(surf, (255, 120, 80), False, sp, max(1, int(self.width * self.scale)))
        if self.canvas.collidepoint(mp) and self.tool in ("bohrer", "beitel"):
            pygame.draw.circle(surf, (255, 200, 150), mp, max(2, int(self.width / 2 * self.scale)), 1)
        surf.set_clip(None)
        # tools
        for i, (k, de, en) in enumerate(TOOLS):
            rect = pygame.Rect(r.x + 16, r.y + 80 + i * 40, 220, 34)
            panel(surf, rect, 230 if self.tool == k else 170, border=GOLD if self.tool == k else (90, 80, 60))
            text(surf, f"{i + 1}  {de} ({en})", (rect.x + 10, rect.y + 8), 14, (240, 230, 210))
            self.rects.append((rect, "tool", k))
        text(surf, f"Breite (width): {self.width:.0f}", (r.x + 16, r.y + 250), 12, (200, 190, 170))
        n_b, per, L = self.split_yield()
        rect = pygame.Rect(r.x + 16, r.y + 440, 220, 46)
        panel(surf, rect, 220 if n_b else 140, border=GOLD if n_b else (90, 80, 60))
        text(surf, "5  Spalten (split into planks)", (rect.x + 10, rect.y + 6), 14, (240, 230, 210))
        text(surf, f"→ {n_b * per} Bretter ({n_b} boards × {per})" if n_b else "too thin or too short to split",
             (rect.x + 10, rect.y + 26), 11, (200, 190, 160))
        self.rects.append((rect, "split", None))
        for i, (kind, label) in enumerate((("undo", "Rückgängig (Z)"), ("finish", "Fertig (Enter)"),
                                           ("cancel", "Abbrechen (Esc)"))):
            rect = pygame.Rect(r.x + 16, r.y + 280 + i * 40, 220, 34)
            panel(surf, rect, 200)
            text(surf, label, (rect.x + 10, rect.y + 8), 14)
            self.rects.append((rect, kind, None))
        # what it looks like so far
        tx = c.right + 20
        text(surf, "Erkannt (recognised): " + (f"{SH.TEMPLATES[key][1]} — Güte {int(q * 100)}%" if key else
                                               "Rohling (no known shape)"), (c.x, c.bottom + 12), 15, GERMAN_COLOR)
        text(surf, "Formen (shapes) — click one for a guide:", (tx, r.y + 80), 13, GERMAN_COLOR)
        sc = {k_: s for s, k_, _, _ in ranking}
        for i, k_ in enumerate(SH.TEMPLATES):
            item, de, en = SH.TEMPLATES[k_][0], SH.TEMPLATES[k_][1], SH.TEMPLATES[k_][2]
            y = r.y + 104 + i * 26
            rect = pygame.Rect(tx, y, r.right - tx - 16, 24)
            if rect.collidepoint(mp) or self.target == k_:
                pygame.draw.rect(surf, (70, 60, 40), rect, border_radius=3)
            text(surf, f"{de} ({en})", (tx + 4, y + 4), 12, (236, 228, 210))
            bar(surf, rect.right - 70, y + 9, 60, 6, max(0.0, sc.get(k_, 0.0)), (120, 190, 110) if sc.get(k_, 0) >=
                0.6 else (170, 140, 90))
            self.rects.append((rect, "target", k_))
