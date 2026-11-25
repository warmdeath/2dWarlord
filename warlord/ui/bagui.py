"""The bag view: the Rucksack opened on a cloth, everything you carry lying on it as little piles.

Left click a thing: into your hand (the belt slot you have selected) or put it on (armour, shield, helmet).
Right click: use it (eat, bind wounds) or, for anything else, drop one on the ground.
1-4 while hovering: put it on that belt slot. Recipes for the workshops you stand next to are on the right.
"""
import math
import random

import pygame

from ..settings import SCREEN_W, SCREEN_H, GOLD, GERMAN_COLOR, TILE
from ..items.items import ITEMS, weight
from ..items import crafting as CR
from ..combat.weapons import WEAPONS, HELMET_NAMES
from .common import text, panel, item_icon, ltext, bar

CLOTH = (126, 104, 74)
CLOTH_D = (104, 84, 58)


def _cloth(surf, r, seed=3):
    pygame.draw.rect(surf, CLOTH, r, border_radius=14)
    rng = random.Random(seed)
    for i in range(0, r.w, 9):
        pygame.draw.line(surf, CLOTH_D, (r.x + i, r.y + 4), (r.x + i, r.bottom - 4), 1)
    for _ in range(40):
        x = rng.randint(r.x + 10, r.right - 10)
        y = rng.randint(r.y + 10, r.bottom - 10)
        pygame.draw.line(surf, (140, 118, 86), (x, y), (x + rng.randint(-14, 14), y + rng.randint(-3, 3)), 1)
    pygame.draw.rect(surf, (70, 54, 36), r, 3, border_radius=14)
    # the open flap and the drawstring
    pygame.draw.polygon(surf, (96, 76, 52), [(r.x + 30, r.y), (r.right - 30, r.y), (r.right - 60, r.y - 26),
                                             (r.x + 60, r.y - 26)])
    pygame.draw.line(surf, (190, 160, 110), (r.x + 60, r.y - 18), (r.right - 60, r.y - 18), 2)


def layout(inv, area):
    """Piles on the cloth, grouped by kind; positions stay put between openings."""
    keys = inv.keys_sorted()
    cols = max(1, area.w // 96)
    pos = {}
    for i, k in enumerate(keys):
        cx = area.x + 48 + (i % cols) * 96 + ((i // cols) % 2) * 18
        cy = area.y + 46 + (i // cols) * 86
        rng = random.Random(hash(k) & 0xFFFF)
        pos[k] = (cx + rng.uniform(-8, 8), cy + rng.uniform(-6, 6), rng.uniform(-0.3, 0.3))
    return pos


def draw_pile(surf, key, n, x, y, ang):
    d = ITEMS[key]
    show = min(n, 6 if d.icon in ("log", "block", "lump", "seeds", "arrow", "bread", "berry", "sheaf") else 1)
    rng = random.Random(hash(key) & 0xFFFF)
    for i in range(show):
        ox = rng.uniform(-14, 14) if show > 1 else 0
        oy = -i * 3 + rng.uniform(-3, 3) if show > 1 else 0
        r = pygame.Rect(0, 0, 40, 40)
        r.center = (x + ox, y + oy)
        # a soft shadow under each thing
        pygame.draw.ellipse(surf, (90, 70, 48), (r.x + 6, r.bottom - 8, 30, 8))
        item_icon(surf, key, r)


def draw_bag(ui, surf):
    g = ui.g
    p = g.player
    inv = p.inv
    mp = pygame.mouse.get_pos()
    r = panel(surf, (30, 30, SCREEN_W - 60, SCREEN_H - 60), 235)
    ltext(surf, "Rucksack", (r.x + 16, r.y + 10), 22, GOLD)
    text(surf, "Left: take in hand / put on · Right: use or drop one · 1-4 over a thing: onto the belt · I/Esc close",
         (r.x + 16, r.y + 40), 12, (190, 190, 180))
    cloth = pygame.Rect(r.x + 18, r.y + 92, 640, r.h - 120)
    _cloth(surf, cloth)
    ui.inv_rects = []
    pos = layout(inv, cloth)
    tip = None
    for k, (x, y, a) in pos.items():
        n = inv.count(k)
        draw_pile(surf, k, n, x, y, a)
        rect = pygame.Rect(x - 28, y - 28, 56, 56)
        if n > 1:
            text(surf, f"×{n}", (x + 22, y + 12), 12, (250, 240, 210), right=True)
        if k in inv.belt:
            pygame.draw.circle(surf, GOLD, (int(x - 22), int(y - 20)), 8)
            text(surf, str(inv.belt.index(k) + 1), (x - 22, y - 27), 11, (30, 24, 20), center=True, shadow=False)
        q = inv.quality.get(k)
        if q is not None:
            bar(surf, x - 18, y + 24, 36, 3, q, (200, 180, 90))
        if rect.collidepoint(mp):
            pygame.draw.rect(surf, (255, 236, 170), rect, 1, border_radius=6)
            tip = k
        ui.inv_rects.append((rect, "item", k))
    # weight
    wt = inv.weight()
    frac = wt / inv.capacity
    text(surf, f"Gewicht (weight): {wt:.1f} / {inv.capacity:.0f} kg", (cloth.x, cloth.y - 34), 13,
         (230, 210, 170) if frac < 0.9 else (240, 140, 110))
    bar(surf, cloth.x + 250, cloth.y - 30, 200, 8, min(1.0, frac), (190, 160, 90) if frac < 0.9 else (220, 90, 70))
    if getattr(p, "carrying", None) is not None:
        o = p.carrying
        nm = ITEMS[o.item].de if o.item in ITEMS else "Stamm"
        text(surf, f"In den Armen (in your arms): {nm} — too bulky for the bag", (cloth.x + 470, cloth.y - 34), 12,
             (210, 200, 170))
    # the belt
    bx = r.x + 690
    text(surf, "Gürtel (belt):", (bx, r.y + 92), 14, GERMAN_COLOR)
    for i in range(inv.BELT):
        rect = pygame.Rect(bx + i * 58, r.y + 114, 52, 52)
        panel(surf, rect, 200, border=GOLD if i == inv.selected else (90, 80, 60))
        k = inv.belt[i]
        if k:
            item_icon(surf, k, rect.inflate(-6, -6))
            if rect.collidepoint(mp):
                tip = k
        text(surf, str(i + 1), (rect.x + 4, rect.y + 2), 10, (200, 190, 160))
        ui.inv_rects.append((rect, "belt", i))
    # equipment
    ey = r.y + 186
    text(surf, "Ausrüstung (worn):", (bx, ey), 14, GERMAN_COLOR)
    eq = [("Schild", p.shield.de if p.shield else "—", "shield"), ("Rüstung", p.armor.de, "armor"),
          ("Helm", HELMET_NAMES[p.helmet][0] if p.helmet else "—", "helmet")]
    for i, (lab, val, kind) in enumerate(eq):
        rect = pygame.Rect(bx, ey + 22 + i * 20, 300, 18)
        text(surf, f"{lab}: {val}", (rect.x, rect.y), 13)
        ui.inv_rects.append((rect, "unequip", kind))
    wd = p.weapon_def
    text(surf, f"In der Hand: {wd.de} — {wd.dmg:.0f} dmg, reach {wd.reach:.0f}", (bx, ey + 88), 12,
         (190, 190, 180))
    # recipes for the workshops around you
    st = CR.stations_near(g.world, int(p.cx // TILE), int(p.cy // TILE))
    ry = ey + 118
    text(surf, "Handwerk (crafting) — near: " + (", ".join(sorted(st)) if st else "nothing (hands only)"),
         (bx, ry), 13, GERMAN_COLOR)
    text(surf, "Wood is shaped, not crafted: C at a log, or E at a Werkbank.", (bx, ry + 18), 11, (170, 170, 160))
    rows = CR.available(inv, st)
    rows.sort(key=lambda t: (not t[1], not t[2]))
    start = ui.scroll
    for i, (rec, can, station_ok) in enumerate(rows[start:start + 17]):
        y = ry + 40 + i * 21
        rect = pygame.Rect(bx, y, r.right - bx - 16, 19)
        d = ITEMS[rec.out]
        col = (230, 230, 220) if can else (140, 140, 130) if station_ok else (100, 90, 80)
        if rect.collidepoint(mp) and can:
            pygame.draw.rect(surf, (70, 60, 40), rect, border_radius=3)
        needs = ", ".join(f"{n} {ITEMS[k].de}" for k, n in rec.needs.items())
        stn = f" @{rec.station}" if rec.station else ""
        text(surf, f"{rec.n}× {d.de} ({d.en}) ← {needs}{stn}", (rect.x + 4, y + 2), 12, col, shadow=False)
        ui.inv_rects.append((rect, "recipe", rec))
        if rect.collidepoint(mp):
            tip = rec.out
    if tip:
        d = ITEMS[tip]
        extra = f" — {weight(tip):.1f} kg"
        if d.weapon:
            extra += " — " + WEAPONS[d.weapon].note
        q = inv.quality.get(tip)
        if q is not None:
            extra += f" — Güte {int(q * 100)}%"
        mx, my = mp
        line = f"{d.de} ({d.en}){extra}"
        tw = min(620, ui.small.size(line)[0] + 20)
        panel(surf, (min(mx + 14, SCREEN_W - tw - 4), my + 10, tw, 26), 240)
        text(surf, line, (min(mx + 22, SCREEN_W - tw + 4), my + 14), 13)


def bag_click(ui, pos, button):
    g = ui.g
    p = g.player
    inv = p.inv
    for rect, kind, val in getattr(ui, "inv_rects", []):
        if not rect.collidepoint(pos):
            continue
        if kind == "item":
            d = ITEMS[val]
            if button == 3:
                if d.cat == "food":
                    g.eat(p, val)
                elif d.cat == "heal":
                    g.bandage(p)
                else:
                    inv.remove(val, 1)
                    g.drop_item(val, 1, p.cx + p.facing * 30, p.y)
                g.sync_held()
                return
            if d.cat == "shield":
                p.equip(shield=val)
            elif d.cat == "armor":
                p.equip(armor=val)
            elif d.cat == "helmet":
                p.equip(helmet=val)
            else:
                inv.to_belt(val, inv.selected)
                g.sync_held()
                ui.toast(f"In der Hand: [{d.de}|{d.en}]", 1.5)
            return
        if kind == "belt":
            inv.selected = val
            g.sync_held()
            return
        if kind == "recipe":
            r = val
            st = CR.stations_near(g.world, int(p.cx // TILE), int(p.cy // TILE))
            if (r.station is None or r.station in st) and inv.take(r.needs):
                left = inv.add(r.out, r.n)
                if left:
                    g.drop_item(r.out, left, p.cx, p.y)
                p.stats["crafted"] += 1
                g.sync_held()
                g.sfx("place")
                d = ITEMS[r.out]
                ui.toast(f"[Hergestellt|crafted]: {r.n}× [{d.de}|{d.en}]", 2)
                g.emit("craft", key=r.out)
            return
        if kind == "unequip":
            if val == "shield":
                p.equip(shield="")
            elif val == "armor":
                p.equip(armor="kleidung")
            elif val == "helmet":
                p.equip(helmet="")
            return


def bag_key(ui, k):
    """1-4 while hovering a thing puts it on that belt slot."""
    if not (pygame.K_1 <= k <= pygame.K_4):
        return False
    mp = pygame.mouse.get_pos()
    inv = ui.g.player.inv
    for rect, kind, val in getattr(ui, "inv_rects", []):
        if kind == "item" and rect.collidepoint(mp):
            inv.to_belt(val, k - pygame.K_1)
            ui.g.sync_held()
            return True
    return False
