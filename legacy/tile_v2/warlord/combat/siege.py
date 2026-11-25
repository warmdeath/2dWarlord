"""Belagerung — siege warfare, German style, c. 1300.

Defences  : Graben (moat), Zugbrücke (drawbridge), Fallgatter (portcullis), Pechnase (machicolation)
Engines   : Rammbock under a 'Katze' roof, Blide (counterweight trebuchet), Belagerungsturm (siege tower),
            Donnerbüchse (an experimental powder gun — rare, loud, and liable to burst)
Assault   : Sturmleitern (ladders: real tiles that real soldiers climb, and that defenders can push away),
            Mineure (sappers: dig a real tunnel, prop the wall on timber, burn the props -> the wall falls),
            Rampe (attackers stuck in a moat shovel earth into it until they can climb out)
Everything acts on the tile world, so the physics engine decides what stands and what falls.
"""
import math
import random

import pygame

from ..settings import TILE
from ..world import tiles as T

ENGINES = {
    #           de                    en                  w    h    hp   crew speed reload
    "ramm": ("Rammbock", "battering ram", 64, 40, 260, 8, 34, 2.4),
    "turm": ("Belagerungsturm", "siege tower", 52, 176, 420, 12, 26, 0.7),
    "blide": ("Blide", "trebuchet", 76, 120, 260, 6, 0, 14.0),
    "buechse": ("Donnerbüchse", "powder gun", 44, 26, 140, 3, 0, 22.0),
}


# ================================================================== defences
def set_defenses(game, gh, closed):
    """Raise the drawbridge and drop the portcullis (closed) — or the reverse."""
    w = game.world
    if gh.get("closed") == closed:
        return
    gh["closed"] = closed
    if closed:
        for (x, y) in gh["bridge"]:
            if w.fg[x, y] == T.BRIDGE.id:
                w.set(x, y, 0)
        for (x, y) in gh["bridge_up"]:
            if w.fg[x, y] == 0:
                w.set(x, y, T.BRIDGE_UP.id)
        for (x, y) in gh["portcullis"]:
            if w.fg[x, y] in (0, T.PORTCULLIS_UP.id):
                w.set(x, y, T.PORTCULLIS.id)
        game.sfx("gate")
    else:
        for (x, y) in gh["bridge_up"]:
            if w.fg[x, y] == T.BRIDGE_UP.id:
                w.set(x, y, 0)
        for (x, y) in gh["bridge"]:
            if w.fg[x, y] == 0:
                w.set(x, y, T.BRIDGE.id)
        for (x, y) in gh["portcullis"]:
            if w.fg[x, y] == T.PORTCULLIS.id:
                w.set(x, y, T.PORTCULLIS_UP.id)
        game.sfx("gate")


def gatehouse_owner(game, gh):
    s = game.world.settlement_at(gh["x"], margin=24)
    if s is None:
        return getattr(gh, "owner", None) or gh.get("owner")
    if s["type"] == "robber":
        return "bandit"
    si = game.world.settlements.index(s)
    return game.society.owner.get(si, s["kingdom"])


def pour_pitch(game, gh, by=None):
    """Boiling pitch through the machicolation: burns whatever stands below."""
    px, py = gh["pechnase"]
    x = px * TILE + 8
    for _ in range(14):
        game.fx._p(x + random.uniform(-4, 4), (py + 1) * TILE, random.uniform(-20, 20), random.uniform(60, 160),
                   1.0, (30, 24, 20), 3, 900)
    game.fx.fire(x, gh["g"] * TILE - 6, 10)
    game.fx.text(x, py * TILE - 10, "Pech!", (255, 160, 90), gloss="boiling pitch!")
    game.sfx("hiss")
    side = gatehouse_owner(game, gh)
    for hf in game.formations:
        if hf.dead or not game.hostile_factions(hf.side, side):
            continue
        a, b = hf.span()
        if a - 24 <= x <= b + 24:
            for _ in range(random.randint(2, 4)):
                hf._kill_member(x)
            hf.morale -= 12
    for h in game.targets_near(x, 40):
        if not getattr(h, "dead", False) and h.feet > py * TILE:
            h.take_hit(game, by, 30, "blunt", 30, ("unblockable",), source_x=x)
    for e in game.engines:
        if abs(e.x - x) < e.w / 2 + 20:
            e.burning = max(e.burning, 12.0)


# ================================================================== engines
class SiegeEngine:
    kind = "engine"

    def __init__(self, game, key, x, side, facing, colors=((120, 120, 120), (220, 220, 220))):
        spec = ENGINES[key]
        self.key = key
        self.de, self.en = spec[0], spec[1]
        self.w, self.h = spec[2], spec[3]
        self.hp = self.max_hp = float(spec[4])
        self.crew = spec[5]
        self.speed = spec[6]
        self.reload_time = spec[7]
        self.reload = spec[7] * random.uniform(0.3, 0.8)
        self.x = float(x)
        self.side = side
        self.faction = side
        self.facing = facing
        self.colors = colors
        self.active = side != "player"
        self.burning = 0.0
        self.removed = False
        self.dead = False
        self.row = None
        self.anim = 0.0
        self.fire_anim = 0.0
        self.docked = False
        self.dock_t = 0.0
        self.strike_t = 0.0
        self.uid = id(self)
        self.blocked = None
        self.carry = None          # Haufen riding the siege tower
        self.smoke = 0.0

    # geometry ---------------------------------------------------------------
    def ground(self, game):
        w = game.world
        tx = max(0, min(w.w - 1, int(self.x // TILE)))
        if self.row is None:
            self.row = w.ground_at(tx, max(0, int(w.surface[tx]) - 30))
        row = w.ground_at(tx, max(0, self.row - 2))
        if row >= self.row - 2 and row < w.h:
            self.row = row
        return self.row * TILE

    @property
    def cx(self):
        return self.x

    def rect(self, game):
        gy = self.ground(game)
        return (self.x - self.w / 2, gy - self.h, self.w, self.h)

    def contains(self, game, px, py):
        x, y, w, h = self.rect(game)
        return x <= px <= x + w and y <= py <= y + h

    # damage -----------------------------------------------------------------
    def damage(self, game, amount, crew_chance=0.0, fire=False):
        self.hp -= amount
        if fire:
            self.burning = max(self.burning, 10.0)
        if random.random() < crew_chance and self.crew > 0:
            self.crew -= 1
            game.fx.blood(self.x, self.ground(game) - 20, 6)
        if self.hp <= 0 and not self.dead:
            self.destroy(game)

    def destroy(self, game, burst=False):
        self.dead = True
        self.removed = True
        gy = self.ground(game)
        game.fx.debris(self.x, gy - self.h / 2, (120, 86, 52), 30)
        game.fx.smoke(self.x, gy - self.h / 2, 12)
        game.fx.text(self.x, gy - self.h - 20, f"{self.de} zerstört!", (255, 170, 120), gloss=f"{self.en} destroyed")
        game.camera.shake = max(game.camera.shake, 5)
        game.sfx("collapse")
        if self.carry is not None:
            self.carry.riding = None
        game.emit("engine_destroyed", engine=self)

    # update -----------------------------------------------------------------
    def update(self, game, dt):
        if self.dead:
            return
        self.anim += dt
        self.fire_anim = max(0.0, self.fire_anim - dt)
        self.smoke = max(0.0, self.smoke - dt)
        if self.burning > 0:
            self.burning -= dt * (3.0 if game.env.is_raining() else 1.0)
            self.hp -= 7 * dt
            if random.random() < 0.6:
                game.fx.fire(self.x + random.uniform(-self.w / 2, self.w / 2), self.ground(game) - random.uniform(0, self.h),
                             1)
            if self.hp <= 0:
                self.destroy(game)
                return
        if self.crew <= 0:
            return            # abandoned
        if self.key in ("ramm", "turm") and self.active:
            self._advance(game, dt)
        elif self.key in ("blide", "buechse") and self.active:
            self.reload -= dt * min(1.0, self.crew / 3.0)
            if self.reload <= 0:
                tgt = self._find_target(game)
                if tgt is not None:
                    self._fire(game, tgt)
                    self.reload = self.reload_time * random.uniform(0.9, 1.15)
                else:
                    self.reload = 1.0

    def _advance(self, game, dt):
        w = game.world
        gy = self.ground(game)
        feet = int(gy // TILE) - 1
        lead = self.x + self.facing * (self.w / 2 + 2)
        tx = int(lead // TILE)
        blocked = None
        # how tall is whatever is in front of us? wheels roll up a step of up to 2 tiles
        height = 0
        while height < 6 and w.inside(tx, feet - height) and T.SOLID[w.fg[tx, feet - height]]:
            height += 1
        if height > 2 or (height and any(w.inside(tx, feet - k) and T.SOLID[w.fg[tx, feet - k]]
                                         for k in range(height + 1, height + 3))):
            for ty in range(feet - 3, feet + 1):
                if w.inside(tx, ty) and T.SOLID[w.fg[tx, ty]]:
                    blocked = (tx, ty)
                    break
        elif height:
            self.row -= height   # climb the step
        # a drop we can't roll down (an unfilled moat)
        drop = w.ground_at(tx, max(0, self.row - 2)) - self.row
        if blocked is None and drop > 2:
            self.blocked = ("drop", tx)
            return
        self.blocked = blocked
        if blocked is None:
            self.docked = False
            self.x += self.facing * self.speed * dt * min(1.0, self.crew / 4.0)
            return
        if self.key == "ramm":
            self.strike_t -= dt
            if self.strike_t <= 0:
                self.strike_t = self.reload_time
                self.fire_anim = 0.5
                bx = blocked[0]
                hit = False
                for ty in range(feet - 3, feet + 1):
                    if w.inside(bx, ty) and T.SOLID[w.fg[bx, ty]]:
                        game.damage_tile(bx, ty, 5.5 * min(1.0, self.crew / 5.0), None)
                        hit = True
                if hit:
                    game.fx.debris(bx * TILE + 8, (feet - 1) * TILE, (110, 80, 50), 8)
                    game.camera.shake = max(game.camera.shake, 3)
                    game.sfx("impact")
                    game.fx.text(bx * TILE, (feet - 4) * TILE, "Rumms!", (240, 210, 160), gloss="thud!", life=0.7)
        elif self.key == "turm":
            # dock against the wall and let the men across
            if not self.docked:
                self.docked = True
                game.fx.text(self.x, gy - self.h - 10, "Brücke runter!", (255, 220, 150), gloss="drop the bridge!")
                game.sfx("gate")
            self.dock_t -= dt
            hf = self.carry
            if hf is not None and not hf.dead and hf.members and self.dock_t <= 0:
                self.dock_t = self.reload_time
                top = self._wall_top(game, blocked[0])
                if top is not None:
                    spawn_assault_fighter(game, hf, blocked[0] * TILE + 8 + self.facing * 10, top * TILE)

    def _wall_top(self, game, wx):
        w = game.world
        y = self.row - 1
        while y > 0 and w.inside(wx, y) and T.SOLID[w.fg[wx, y]]:
            y -= 1
        if self.row - y > 13:
            return None
        # stand on the battlement walk just behind the parapet
        return y + 1 if T.SOLID[w.fg[wx, y + 1]] else y

    def _find_target(self, game):
        rng_min, rng_max = (260, 2100) if self.key == "blide" else (80, 1300)
        best = None
        for hf in game.formations:
            if hf.dead or not game.hostile_factions(self.side, hf.side):
                continue
            c = hf.center()
            d = (c[0] - self.x) * self.facing
            if rng_min < d < rng_max and (best is None or d < best[0]):
                best = (d, c[0], c[1])
        # walls and towers of a hostile fortress
        for gh in game.world.gatehouses:
            owner = gatehouse_owner(game, gh)
            if owner is None or not game.hostile_factions(self.side, owner):
                continue
            px = gh["portcullis"][0][0] * TILE + 8
            d = (px - self.x) * self.facing
            if rng_min < d < rng_max and (best is None or d < best[0] * 1.6):
                best = (d, px + self.facing * random.choice((0, 16, 40)), (gh["g"] - random.randint(3, 9)) * TILE)
        if best is None:
            return None
        return best[1], best[2]

    def _fire(self, game, tgt):
        from ..entities.projectile import Projectile
        gy = self.ground(game)
        if self.key == "blide":
            sx, sy = self.x - self.facing * 10, gy - self.h + 10
            g = 600.0
            T_ = 2.6
            dx = (tgt[0] - sx) * random.uniform(0.96, 1.04)
            dy = tgt[1] - sy
            vx = dx / T_
            vy = (dy - 0.5 * g * T_ * T_) / T_
            p = Projectile(sx, sy, vx, vy, None, "stone", 70)
            self.fire_anim = 1.2
            game.sfx("tree")
        else:
            if random.random() < 0.06:
                self._burst(game)
                return
            sx, sy = self.x + self.facing * 22, gy - 16
            g, v = 300.0, 1100.0
            x = abs(tgt[0] - sx)
            y = -(tgt[1] - sy)
            disc = v ** 4 - g * (g * x * x + 2 * y * v * v)
            ang = math.atan((v * v - math.sqrt(disc)) / (g * x)) if disc > 0 and x > 1 else 0.2
            ang += random.uniform(-0.03, 0.03)
            p = Projectile(sx, sy, math.cos(ang) * v * self.facing, -math.sin(ang) * v, None, "ball", 80)
            self.fire_anim = 0.4
            self.smoke = 2.5
            game.fx.flash = max(game.fx.flash, 0.25)
            game.fx.smoke(sx, sy, 18)
            game.fx.sparks(sx, sy, 14)
            game.camera.shake = max(game.camera.shake, 5)
            game.sfx("thunder")
            game.fx.text(self.x, gy - 50, "Donner!", (255, 230, 170), gloss="thunder!")
        p.faction = self.side
        game.projectiles.append(p)

    def _burst(self, game):
        gy = self.ground(game)
        game.fx.text(self.x, gy - 60, "Die Büchse zerspringt!", (255, 120, 80), gloss="the gun bursts!")
        game.fx.flash = 0.6
        game.fx.smoke(self.x, gy - 10, 30)
        game.fx.sparks(self.x, gy - 10, 40)
        for h in game.targets_near(self.x, 70):
            h.take_hit(game, None, 45, "blunt", 50, ("unblockable",), source_x=self.x)
        self.destroy(game, burst=True)

    def toggle(self, game):
        self.active = not self.active
        if self.key in ("blide", "buechse"):
            msg = "[Feuer frei|fire at will]!" if self.active else "[Feuer einstellen|cease fire]!"
        else:
            msg = "[Vorwärts|forward]!" if self.active else "[Halt|halt]!"
        game.player.say(msg, t=2)
        game.hear(msg, "orders")

    # drawing ------------------------------------------------------------------
    def draw(self, surf, ox, oy, game):
        if self.dead:
            return
        gy = self.ground(game)
        x, y = self.x - ox, gy - oy
        if not (-300 < x < surf.get_width() + 300):
            return
        f = self.facing
        wood, dark, light = (128, 90, 54), (86, 60, 36), (156, 116, 72)
        if self.key == "ramm":
            for wx in (-20, 0, 20):
                pygame.draw.circle(surf, dark, (int(x + wx), int(y - 6)), 6)
                pygame.draw.circle(surf, light, (int(x + wx), int(y - 6)), 6, 1)
            swing = math.sin(min(1.0, self.fire_anim * 3) * math.pi) * 10 * f
            log0 = (x - f * 26, y - 18)
            log1 = (x + f * 30 + swing, y - 18)
            pygame.draw.line(surf, (100, 70, 42), log0, log1, 7)
            pygame.draw.polygon(surf, (90, 92, 100), [(log1[0], log1[1] - 5), (log1[0] + f * 8, log1[1]),
                                                      (log1[0], log1[1] + 5)])
            roof = [(x - 32, y - 12), (x + 32, y - 12), (x + 20, y - 40), (x - 20, y - 40)]
            pygame.draw.polygon(surf, (96, 76, 56), roof)
            pygame.draw.polygon(surf, (120, 98, 72), [(x - 32, y - 12), (x, y - 12), (x, y - 40), (x - 20, y - 40)])
            for k in range(4):
                pygame.draw.line(surf, (70, 54, 40), (x - 28 + k * 18, y - 14), (x - 18 + k * 12, y - 38), 1)
            pygame.draw.polygon(surf, (30, 24, 22), roof, 1)
        elif self.key == "turm":
            H = self.h
            body = [(x - 24, y - 8), (x + 24, y - 8), (x + 20, y - H), (x - 20, y - H)]
            pygame.draw.polygon(surf, wood, body)
            pygame.draw.polygon(surf, light, [(x - 24 * f, y - 8), (x, y - 8), (x, y - H), (x - 20 * f, y - H)])
            for k in range(1, 10):
                yy = y - 8 - k * (H - 8) / 10
                pygame.draw.line(surf, dark, (x - 23, yy), (x + 23, yy), 1)
            pygame.draw.polygon(surf, (30, 24, 22), body, 1)
            for k in range(-20, 22, 8):
                pygame.draw.rect(surf, wood, (x + k - 3, y - H - 8, 5, 8))
            for wx in (-16, 16):
                pygame.draw.circle(surf, dark, (int(x + wx), int(y - 6)), 7)
            bx0 = x + f * 20
            if self.docked:
                pygame.draw.line(surf, light, (bx0, y - H + 18), (bx0 + f * 28, y - H + 18), 5)
            else:
                pygame.draw.line(surf, light, (bx0, y - H + 18), (bx0 + f * 6, y - H - 10), 5)
            pygame.draw.rect(surf, self.colors[0], (x - 4, y - H - 26, 10, 7))
        elif self.key == "blide":
            px, py = x, y - 76
            pygame.draw.polygon(surf, dark, [(x - 34, y - 4), (px, py), (x - 26, y - 4)])
            pygame.draw.polygon(surf, wood, [(x + 34, y - 4), (px, py), (x + 26, y - 4)])
            pygame.draw.rect(surf, dark, (x - 38, y - 8, 76, 6))
            # throwing arm: the sling end hangs low behind when cocked, whips up and over when it fires
            cocked, fired = 2.35, -1.05
            if self.fire_anim > 0:
                k = min(1.0, (1.2 - self.fire_anim) / 0.35)
                a_long = cocked + (fired - cocked) * k
            else:
                k = max(0.0, min(1.0, 1.0 - self.reload / max(0.1, self.reload_time)))
                a_long = fired + (cocked - fired) * k
            if f < 0:
                a_long = math.pi - a_long
            ang = a_long + math.pi
            long_end = (px + math.cos(ang + math.pi) * 62, py + math.sin(ang + math.pi) * 62)
            short_end = (px + math.cos(ang) * 22, py + math.sin(ang) * 22)
            pygame.draw.line(surf, light, long_end, short_end, 5)
            cw = [(short_end[0] - 10, short_end[1]), (short_end[0] + 10, short_end[1]),
                  (short_end[0] + 8, short_end[1] + 18), (short_end[0] - 8, short_end[1] + 18)]
            pygame.draw.polygon(surf, (90, 88, 86), cw)
            pygame.draw.polygon(surf, (30, 24, 22), cw, 1)
            pygame.draw.line(surf, (200, 190, 160), long_end, (long_end[0], long_end[1] + 14), 1)
            pygame.draw.circle(surf, (40, 36, 34), (int(px), int(py)), 3)
        else:
            pygame.draw.polygon(surf, wood, [(x - 22, y - 4), (x + 18, y - 4), (x + 14, y - 14), (x - 22, y - 12)])
            pygame.draw.circle(surf, dark, (int(x - 12), int(y - 5)), 6)
            barrel = [(x - 14 * f, y - 22), (x + 24 * f, y - 20), (x + 24 * f, y - 12), (x - 14 * f, y - 10)]
            pygame.draw.polygon(surf, (70, 72, 80), barrel)
            pygame.draw.polygon(surf, (110, 112, 122), [(x - 14 * f, y - 22), (x + 24 * f, y - 20),
                                                        (x + 24 * f, y - 17), (x - 14 * f, y - 18)])
            for k in (-6, 6, 16):
                pygame.draw.line(surf, (40, 40, 44), (x + k * f, y - 22), (x + k * f, y - 10), 2)
            if self.smoke > 0 and random.random() < 0.3:
                game.fx.smoke(self.x + f * 24, gy - 18, 1)
        # health / crew label
        if self.side == "player" or self.hp < self.max_hp:
            bw = 40
            pygame.draw.rect(surf, (30, 30, 30), (x - bw / 2, y - self.h - 30, bw, 4))
            pygame.draw.rect(surf, (210, 140, 60), (x - bw / 2, y - self.h - 30, bw * max(0, self.hp) / self.max_hp, 4))
        if self.side == "player":
            from ..ui.common import text
            st = ("aktiv" if self.active else "wartet") if self.crew > 0 else "verlassen"
            text(surf, f"{self.de} ({st})", (x, y - self.h - 46), 11, (230, 220, 190), center=True)


# ================================================================== the physics of assault
def spawn_assault_fighter(game, hf, x, y):
    """One soldier leaves the formation and fights on the wall."""
    if not hf.members:
        return None
    from ..entities.humanoid import Humanoid
    m = hf.members.pop()
    proto = hf.protos[m["proto"]]
    h = Humanoid(x - 7, y - 43, dict(proto.look), hf.side, hf.unit.de)
    h.equip(weapon=proto.weapon_key, shield=hf.unit.shield or "", armor=hf.unit.armor, helmet=hf.unit.helmet or "")
    h.hp = m["hp"]
    h.brave = True
    h.skill = 0.4 + hf.unit.quality * 0.4
    h.facing = hf.facing
    h.home_brain = "combat"
    h.keep = True
    game.add_humanoid(h, "combat")
    game.assaulters.append(h)
    return h


def ramp(game, hf, dt):
    """Attackers stuck below a bank shovel earth in front of them until they can climb out."""
    w = game.world
    hf.ramp_t = getattr(hf, "ramp_t", 0.0) - dt
    if hf.ramp_t > 0:
        return
    hf.ramp_t = 0.55 / max(1, min(3, len(hf.front)))
    f = hf.facing
    fx = int(hf.x // TILE)
    row = hf.base_row
    for k in range(0, 6):
        cx = fx - f * k
        cy = row - 1
        if w.inside(cx, cy) and not T.SOLID[w.fg[cx, cy]]:
            w.liq[cx, cy] = 0
            w.mark_liquid(cx, cy)
            w.set(cx, cy, T.DIRT.id)
            game.fx.dust(cx * TILE + 8, cy * TILE + 8, 3, (112, 78, 52))
            if random.random() < 0.15:
                hf.shout = ["[Rampe aufschütten|build up the ramp]!", 1.5]
            return
    # this layer is done: everyone steps up one tile
    hf.y_cache.clear()


def ladder(game, hf, blocked, dt):
    """Sturmleitern: raise a ladder against the wall, then climb it one man at a time."""
    w = game.world
    f = hf.facing
    lad = getattr(hf, "ladder", None)
    wx = blocked[0]
    feet = hf.base_row - 1
    if lad is None or lad.get("wx") != wx:
        y = feet
        while y > 0 and w.inside(wx, y) and T.SOLID[w.fg[wx, y]]:
            y -= 1
        height = feet - y
        if height > 14:
            return False
        hf.ladder = lad = {"wx": wx, "x": wx - f, "top": y + 1, "t": 2.5, "up": False, "climb": 0.0}
        hf.shout = ["[Leitern an die Mauer|ladders to the wall]!", 2.0]
    if not lad["up"]:
        lad["t"] -= dt
        if lad["t"] <= 0:
            lad["up"] = True
            for yy in range(lad["top"] - 1, feet + 1):
                if w.inside(lad["x"], yy) and w.fg[lad["x"], yy] == 0:
                    w.set(lad["x"], yy, T.LADDER.id)
            game.ladders.append({"x": lad["x"], "top": lad["top"] - 1, "bottom": feet, "side": hf.side, "t": 0.0,
                                 "hf": hf})
            game.sfx("place")
        return True
    if w.fg[lad["x"], feet] != T.LADDER.id:     # pushed away — raise it again
        hf.ladder = None
        return True
    lad["climb"] -= dt
    if lad["climb"] <= 0 and hf.members:
        lad["climb"] = 1.3
        h = spawn_assault_fighter(game, hf, lad["x"] * TILE + 8, (feet + 1) * TILE)
        if h is not None:
            game.set_brain(h, "climb")
            h.climb_target = (lad["x"], lad["top"], wx)
    return True


def sap(game, hf, blocked, dt):
    """Mineure: dig under the wall, hold it up on timber props, then burn the props."""
    w = game.world
    f = hf.facing
    job = getattr(hf, "sap", None)
    if job is not None and job.get("wx") != blocked[0] and job["lit"]:
        job = None                       # that wall is down: start on the next one
    if job is None:
        wx = blocked[0]
        r0 = hf.base_row
        ex = wx - f * 4
        ops = []
        for y in range(r0, r0 + 4):
            ops.append(("dig", ex, y))
        x = ex + f
        while x != wx:
            for y in (r0 + 1, r0 + 2, r0 + 3):
                ops.append(("dig", x, y))
            x += f
        cols = [wx + f * k for k in range(0, 6)]
        for cx in cols:
            for y in (r0 + 1, r0 + 2, r0 + 3):
                ops.append(("dig", cx, y))
            ops.append(("prop", cx, r0))
        hf.sap = job = {"ops": ops, "i": 0, "t": 0.0, "cols": cols, "row": r0, "lit": False, "fuse": 4.0, "wx": wx}
        hf.shout = ["[Untergraben|undermine]!", 2.0]
    if job["i"] < len(job["ops"]):
        job["t"] -= dt
        if job["t"] > 0:
            return True
        job["t"] = 0.55
        op, x, y = job["ops"][job["i"]]
        job["i"] += 1
        if not w.inside(x, y):
            return True
        if op == "dig":
            if w.fg[x, y] and w.fg[x, y] != T.BEDROCK.id and not T.BUILT[w.fg[x, y]]:
                w.set(x, y, 0)
                w.set_bg(x, y, T.BG_DIRT)
        else:
            if w.fg[x, y] != T.BEDROCK.id:
                w.fg[x, y] = T.PROP.id     # swap foundation for timber in one move
                w.mark(x, y)
        game.fx.dust(x * TILE + 8, y * TILE + 8, 3, (112, 78, 52))
        if job["i"] % 6 == 0:
            game.sfx("dig")
        return True
    if not job["lit"]:
        job["fuse"] -= dt
        if job["fuse"] <= 0:
            job["lit"] = True
            for cx in job["cols"]:
                game.ignite(cx, job["row"])
            hf.shout = ["[Feuer an die Stützen|fire the props]!", 2.5]
            game.fx.text(job["cols"][0] * TILE, (job["row"] - 4) * TILE, "Die Stützen brennen!", (255, 170, 100),
                         gloss="the props are burning!")
    return True


def update(game, dt):
    """Defender reflexes: raise drawbridges, drop portcullises, pour pitch, push ladders away."""
    w = game.world
    px = game.player.cx
    for gh in w.gatehouses:
        gx = gh["x"] * TILE
        if abs(gx - px) > 5200:
            continue
        owner = gatehouse_owner(game, gh)
        if owner is None:
            continue
        threat = None
        for hf in game.formations:
            if hf.dead or hf.routed or not game.hostile_factions(owner, hf.side):
                continue
            d = abs(hf.x - gx)
            if d < 70 * TILE and (threat is None or d < threat[0]):
                threat = (d, hf)
        for e in game.engines:
            if not e.dead and game.hostile_factions(owner, e.side) and abs(e.x - gx) < 70 * TILE:
                threat = threat or (abs(e.x - gx), None)
        if not gh.get("auto", True):
            continue
        if threat is not None:
            gh["calm"] = 0.0
            if not gh.get("closed"):
                set_defenses(game, gh, True)
                game.fx.text(gx, (gh["g"] - 16) * TILE, "Zugbrücke hoch!", (255, 220, 150),
                             gloss="raise the drawbridge!")
            # pitch on whatever stands at the gate
            gh["pitch_t"] = gh.get("pitch_t", 3.0) - dt
            mx = gh["pechnase"][0] * TILE
            near_gate = any(not e.dead and abs(e.x - mx) < e.w / 2 + 24 and game.hostile_factions(owner, e.side)
                            for e in game.engines)
            near_gate = near_gate or any(not hf.dead and hf.span()[0] - 24 <= mx <= hf.span()[1] + 24 and
                                         game.hostile_factions(owner, hf.side) for hf in game.formations)
            if near_gate and gh["pitch_t"] <= 0 and gh.get("pitch", 6) > 0:
                gh["pitch_t"] = 7.0
                gh["pitch"] = gh.get("pitch", 6) - 1
                pour_pitch(game, gh)
        else:
            gh["calm"] = gh.get("calm", 0.0) + dt
            if gh.get("closed") and gh["calm"] > 15:
                set_defenses(game, gh, False)
    # ladders: a defender at the top shoves them off
    for lad in list(game.ladders):
        x, top = lad["x"], lad["top"]
        if w.fg[x, lad["bottom"]] != T.LADDER.id:
            game.ladders.remove(lad)
            continue
        lx, ly = x * TILE + 8, top * TILE
        defender = None
        for h in game.humanoids:
            if h.dead or h.formation is not None or not game.hostile_factions(h.faction, lad["side"]):
                continue
            if abs(h.cx - lx) < 40 and abs(h.feet - ly) < 40:
                defender = h
                break
        if defender is None:
            lad["t"] = 0.0
            continue
        lad["t"] += dt
        if lad["t"] > 2.5:
            for y in range(lad["top"], lad["bottom"] + 1):
                if w.fg[x, y] == T.LADDER.id:
                    w.set(x, y, 0)
            defender.say("[Leiter weg|away with the ladder]!", t=2)
            game.hear("[Leiter weg|away with the ladder]!", "siege")
            game.fx.debris(lx, ly + 40, (140, 100, 60), 12)
            for h in game.humanoids:
                if abs(h.cx - lx) < 12 and ly < h.feet < (lad["bottom"] + 1) * TILE + 4:
                    h.climbing = False
                    h.vx = -lad["hf"].facing * 120 if lad.get("hf") else 0
            game.ladders.remove(lad)
    # assaulters who hold the wall open the gate
    alive = [h for h in game.assaulters if not h.dead and not h.removed]
    game.assaulters = alive
    for gh in w.gatehouses:
        if not gh.get("closed") and not gh.get("forced"):
            continue
        gx = gh["portcullis"][0][0] * TILE
        near = [h for h in alive if abs(h.cx - gx) < 260 and game.hostile_factions(h.faction,
                                                                                    gatehouse_owner(game, gh) or "")]
        if len(near) >= 3:
            gh["held"] = gh.get("held", 0.0) + dt
            if gh["held"] > 8 and not gh.get("forced"):
                gh["forced"] = True
                gh["auto"] = False
                set_defenses(game, gh, False)
                for (x, y) in gh["portcullis"]:
                    for dx in (-1, 0, 1, 2, -2):
                        for yy in range(y - 1, y + 2):
                            if w.inside(x + dx, yy) and w.fg[x + dx, yy] == T.GATE.id:
                                w.set(x + dx, yy, T.GATE_OPEN.id)
                game.fx.text(gx, (gh["g"] - 14) * TILE, "Das Tor ist offen!", (255, 230, 140),
                             gloss="the gate is open!")
                game.sfx("horn")
        else:
            gh["held"] = 0.0


def impact(game, x, y, kind):
    """A trebuchet stone or a powder ball strikes the world."""
    w = game.world
    tx, ty = int(x // TILE), int(y // TILE)
    r = 2 if kind == "stone" else 1
    power = 5.0 if kind == "stone" else 7.5
    for dx in range(-r, r + 1):
        for dy in range(-r, r + 1):
            d = math.hypot(dx, dy)
            if d > r + 0.3:
                continue
            cx, cy = tx + dx, ty + dy
            if w.inside(cx, cy) and w.fg[cx, cy] and T.TILES[int(w.fg[cx, cy])].hardness < 999:
                game.damage_tile(cx, cy, power * (1.0 - d / (r + 1.5)), None)
    game.fx.debris(x, y, (150, 140, 130), 16)
    game.fx.dust(x, y, 14, (160, 150, 140))
    if abs(x - game.player.cx) < 1200:
        game.camera.shake = max(game.camera.shake, 6 if kind == "stone" else 4)
    game.sfx("impact")
    for h in game.targets_near(x, 34):
        if abs(h.cy - y) < 50:
            h.take_hit(game, None, 50, "blunt", 60, ("unblockable",), source_x=x)
    for e in game.engines:
        if not e.dead and e.contains(game, x, y + 4):
            e.damage(game, 70 if kind == "stone" else 90, 0.4)
