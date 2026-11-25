"""Melee and missile resolution, bracing against charges."""
import math

import random

from ..settings import TILE, RUN_SPEED
from . import injury as INJ


def _rect_overlap(a, b):
    return a[0] < b[0] + b[2] and a[0] + a[2] > b[0] and a[1] < b[1] + b[3] and a[1] + a[3] > b[1]


class CombatSystem:
    def __init__(self, game):
        self.game = game
        self.brace_cd = {}

    def hit_rect(self, att, mv):
        reach = mv.reach
        f = att.facing
        x0 = att.cx if f > 0 else att.cx - reach
        if att.mount is not None:
            top, bot = att.y, att.y + att.h + 30
        elif mv.arc in ("thrust", "stab"):
            top, bot = att.y + 4, att.y + 32
        elif mv.arc == "low":
            top, bot = att.y + att.h * 0.45, att.feet + 4
        elif mv.arc == "plunge":
            x0 = att.cx - reach * 0.6 if f < 0 else att.cx - 6
            return (x0, att.y, reach * 0.6 + 12, att.h + 26)
        else:
            top, bot = att.y - 8, att.y + att.h * 0.72
        return (x0, top, reach, bot - top)

    def melee(self, att, mv):
        g = self.game
        r = self.hit_rect(att, mv)
        wd = att.weapon_def
        for t in g.targets_near(att.cx, mv.reach + 40):
            if t is att or t.uid in att.hit_ids or getattr(t, "dead", False):
                continue
            if t is att.mount:
                continue
            if not g.hostile(att, t):
                continue
            tr = (t.x, t.y, t.w, t.h)
            if not _rect_overlap(r, tr):
                continue
            # a crouching fighter ducks under horizontal cuts
            if mv.arc in ("swing", "backswing") and getattr(t, "h", 0) == 28 and getattr(t, "kind", "") == "human" \
                    and att.mount is None:
                if t.uid not in att.hit_ids:
                    g.fx.text(t.cx, t.y - 10, "Geduckt!", (200, 220, 255), gloss="ducked")
                att.hit_ids.add(t.uid)
                continue
            att.hit_ids.add(t.uid)
            dmg = wd.dmg * mv.dmg * att.strength * INJ.damage_factor(att)
            if mv is wd.moves.get("run") and att.mount is None:
                dmg *= 1.0 + min(1.0, abs(att.vx) / RUN_SPEED) * 0.25
            if att.mount is not None:
                speed = abs(att.mount.vx)
                dmg *= 1.0 + speed / (90.0 if "lance" in wd.flags else 220.0)
            if "pike" in wd.flags and abs(t.cx - att.cx) < 30 and att.formation is None:
                dmg *= 0.45  # an enemy inside your pike's reach
            if t is g.player and att is not g.player:
                dmg *= 0.72   # the hero's edge: NPC blows hurt a little less
            flags = wd.flags
            if mv.arc == "plunge":
                flags = flags + ("unblockable",) if t.y > att.y + 10 else flags
            high = mv.arc in ("swing", "backswing", "overhead", "plunge")
            if hasattr(t, "take_hit"):
                if mv.arc == "overhead" or mv.arc == "plunge":
                    hy = t.y + t.h * random.uniform(0.0, 0.45)
                elif mv.arc == "low":
                    hy = t.y + t.h * random.uniform(0.55, 0.95)
                else:
                    hy = max(t.y, min(t.y + t.h - 1, r[1] + r[3] * random.uniform(0.2, 0.85)))
                res = t.take_hit(g, att, dmg, wd.dtype, wd.posture * mv.posture, flags, high=high, hit_y=hy,
                                 pen=INJ.PEN.get(wd.key, 3) + (1 if att.mount is not None else 0))
                if res in ("hit", "block"):
                    g.hitstop(0.035 if res == "hit" else 0.02)
                    if res == "hit":
                        g.camera.shake = max(g.camera.shake, 2.5)
                if res == "parry":
                    return
        # siege engines can be hacked apart (axes best) or set alight with torches
        for e in getattr(g, "engines", []):
            if e.dead or e.uid in att.hit_ids or not g.hostile_factions(att.faction, e.side):
                continue
            ex, ey, ew, eh = e.rect(g)
            if _rect_overlap(r, (ex, ey, ew, eh)):
                att.hit_ids.add(e.uid)
                e.damage(g, wd.dmg * mv.dmg * (1.8 if wd.key == "axt" else 0.6), 0.25 if e.key != "ramm" else 0.08,
                         fire="fire" in wd.flags)
        # tools & torches interact with tiles
        if "fire" in wd.flags:
            tx = int((att.cx + att.facing * mv.reach * 0.8) // TILE)
            ty = int((att.y + 16) // TILE)
            for dy in (0, 1, -1):
                g.try_ignite_tile(tx, ty + dy)

    def update(self, dt):
        """Braced spears & pikes punish anything charging into them."""
        g = self.game
        for k in list(self.brace_cd):
            self.brace_cd[k] -= dt
            if self.brace_cd[k] <= 0:
                del self.brace_cd[k]
        for h in g.humanoids:
            if h.dead or not h.blocking or "brace" not in h.weapon_def.flags:
                continue
            braced = h.state == "crouch" or h.formation_stance == "igel"
            if not braced:
                continue
            reach = h.weapon_def.reach
            for t in g.targets_near(h.cx, reach + 60):
                if t is h or getattr(t, "dead", False) or not g.hostile(h, t):
                    continue
                rider_speed = abs(t.mount.vx) if getattr(t, "mount", None) is not None else abs(t.vx)
                toward = (t.cx - h.cx) * h.facing > 0 and (h.cx - t.cx) * (
                    t.mount.vx if getattr(t, "mount", None) is not None else t.vx) > 0
                dist = abs(t.cx - h.cx)
                if toward and dist < reach and rider_speed > 110 and (h.uid, t.uid) not in self.brace_cd:
                    self.brace_cd[(h.uid, t.uid)] = 0.8
                    dmg = h.weapon_def.dmg * (rider_speed / 55.0)
                    g.fx.text(t.cx, t.y - 20, "Aufgespießt!", (255, 120, 80), gloss="impaled on the brace")
                    if getattr(t, "mount", None) is not None:
                        horse = t.mount
                        horse.take_hit(g, h, dmg * 0.8, "pierce", 40)
                        horse.vx *= -0.3
                        g.dismount(t, thrown=True)
                    t.take_hit(g, h, dmg, "pierce", 40, ("unblockable",))
                    t.vx = -h.facing * -1 * 0 + (h.facing * 160)

    def projectile_hit(self, p):
        g = self.game
        for t in g.targets_near(p.x, 30):
            if t is p.owner or getattr(t, "dead", False):
                continue
            if p.faction is not None and not g.hostile_factions(p.faction, t.faction, p.owner, t):
                continue
            if t.x <= p.x <= t.x + t.w and t.y <= p.y <= t.y + t.h:
                speed = math.hypot(p.vx, p.vy)
                dmg = p.dmg * min(1.4, speed / 650.0)
                if g.env.is_raining() and p.kind != "bolt":
                    dmg *= 0.8
                high = p.y < t.y + 12
                flags = ("armorpierce",) if p.kind == "bolt" else ()
                if hasattr(t, "take_hit"):
                    pen = INJ.PEN.get(p.kind, 5) * min(1.2, speed / 700.0)
                    res = t.take_hit(g, p.owner, dmg, "pierce" if p.kind != "ball" else "blunt", 6, flags, high=high,
                                     source_x=p.x - p.vx * 0.05, arrow=True, hit_y=p.y, pen=pen)
                    if res == "block":
                        g.fx.text(t.cx, t.y - 8, "Tock!", (220, 200, 160))
                if p.fire and hasattr(t, "burning"):
                    t.burning = 3.0
                p.removed = True
                return True
        for e in getattr(g, "engines", []):
            if e.dead or not g.hostile_factions(p.faction, e.side) or not e.contains(g, p.x, p.y):
                continue
            if p.kind in ("stone", "ball"):
                e.damage(g, 80, 0.5)
            else:
                roofed = e.key in ("ramm", "turm")
                e.damage(g, 2, 0.04 if roofed else 0.18, fire=p.fire)
            p.removed = True
            return True
        for hf in g.formations:
            if hf.side == p.faction or hf.dead:
                continue
            if p.kind in ("stone", "ball") and hf.contains(p.x, p.y + 10):
                for _ in range(random.randint(2, 5) if p.kind == "stone" else random.randint(2, 4)):
                    hf._kill_member(p.x)
                hf.morale -= 8
                from . import siege
                siege.impact(g, p.x, p.y + 8, p.kind)
                p.removed = True
                return True
            if not g.hostile_factions(p.faction, hf.side, p.owner, None):
                continue
            if hf.contains(p.x, p.y):
                if hf.arrow_hit(g, p):
                    p.removed = True
                    return True
        return False
