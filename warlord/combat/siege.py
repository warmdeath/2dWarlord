"""Belagerung — siege warfare, German style, c. 1300.

Defences  : Graben (moat), Zugbrücke (drawbridge), Fallgatter (portcullis), Pechnase (machicolation)
Engines   : Rammbock under a 'Katze' roof, Blide (counterweight trebuchet), Belagerungsturm (siege tower),
            Donnerbüchse (an experimental powder gun — rare, loud, and liable to burst)
Assault   : Sturmleitern (ladders: real objects that real soldiers climb, and that defenders push away),
            Mineure (sappers: dig a real tunnel, prop the wall on timber, burn the props -> the wall falls),
            Rampe (attackers stuck in a moat shovel earth into it until they can climb out)
Everything acts on the polygon world: walls are pieces with a support graph, so what loses its footing
falls as rigid bodies.
"""
import math
import random

import pygame

from ..settings import TILE
from ..poly import prefab as PF
from ..poly.objects import PhysObject
from ..poly.materials import MATS

ENGINES = {
    #           de                    en                  w    h    hp   crew speed reload
    "ramm": ("Rammbock", "battering ram", 64, 40, 260, 8, 34, 2.4),
    "turm": ("Belagerungsturm", "siege tower", 52, 176, 420, 12, 26, 0.7),
    "blide": ("Blide", "trebuchet", 76, 120, 260, 6, 0, 14.0),
    "buechse": ("Donnerbüchse", "powder gun", 44, 26, 140, 3, 0, 22.0),
}


# ================================================================== defences
def set_defenses(game, gh, closed):
    """Raise the drawbridge and drop the portcullis (closed) — or the reverse. The winch does the rest."""
    if gh.closed == closed:
        return
    gh.closed = closed
    game.sfx("gate")


def gatehouse_near(game, x, r=400):
    best, bd = None, r
    for gh in game.world.gatehouses:
        d = abs(gh.hinge[0] - x)
        if d < bd:
            best, bd = gh, d
    return best


def gatehouse_owner(game, gh):
    s = game.world.settlement_at(gh.x, margin=24)
    if s is None:
        return gh.owner
    if s["type"] == "robber":
        return "bandit"
    si = game.world.settlements.index(s)
    return game.society.owner.get(si, s["kingdom"])


def pour_pitch(game, gh, by=None):
    """Boiling pitch through the machicolation: burns whatever stands below."""
    x, py = gh.pechnase
    x -= gh.side * 4
    gy = gh.hinge[1]
    for _ in range(14):
        game.fx._p(x + random.uniform(-4, 4), py + 14, random.uniform(-20, 20), random.uniform(60, 160),
                   1.0, (30, 24, 20), 3, 900)
    game.fx.fire(x, gy - 6, 10)
    game.fx.text(x, py - 10, "Pech!", (255, 160, 90), gloss="boiling pitch!")
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
        if not getattr(h, "dead", False) and h.feet > py + 20:
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
        if self.row is None:
            self.row = w.ground_y(self.x, w.surface_y(self.x) - 300, 700)
        gy = w.ground_y(self.x, self.row - 30, 200)
        if gy >= self.row - 28 and gy < w.pixel_h():
            self.row = gy
        return self.row

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
        lead = self.x + self.facing * (self.w / 2 + 2)
        blocked = None
        # wheels roll up a step of up to 2 tiles; anything taller stops us
        for hgt in (36, 52, 70, 100):
            if w.solid_point(lead, gy - hgt):
                pc = PF.piece_at(w, lead, gy - hgt, solid_only=True)
                blocked = pc if pc is not None else ("bank", lead, gy - hgt)
                break
        # a drop we can't roll down (an unfilled moat)
        ahead = w.ground_y(lead, gy - 30, 300)
        if blocked is None and ahead - gy > 34:
            self.blocked = ("drop", lead)
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
                hit = False
                for hgt in (12, 28, 44):
                    pc = PF.piece_at(w, lead + self.facing * 3, gy - hgt, solid_only=True)
                    if pc is not None:
                        power = 16.0 * min(1.0, self.crew / 5.0) * (2.0 if pc.role == "door" else 1.0)
                        game.damage_piece(pc, power / max(0.5, MATS[pc.mat].hard), impulse=(self.facing * 400, 0))
                        hit = True
                if hit:
                    game.fx.debris(lead, gy - 30, (110, 80, 50), 8)
                    game.camera.shake = max(game.camera.shake, 3)
                    game.sfx("impact")
                    game.fx.text(lead, gy - 70, "Rumms!", (240, 210, 160), gloss="thud!", life=0.7)
        elif self.key == "turm":
            if not self.docked:
                self.docked = True
                game.fx.text(self.x, gy - self.h - 10, "Brücke runter!", (255, 220, 150), gloss="drop the bridge!")
                game.sfx("gate")
            self.dock_t -= dt
            hf = self.carry
            if hf is not None and not hf.dead and hf.members and self.dock_t <= 0:
                self.dock_t = self.reload_time
                top = self._wall_top(game, lead + self.facing * 8)
                if top is not None:
                    spawn_assault_fighter(game, hf, lead + self.facing * 14, top)

    def _wall_top(self, game, wx):
        """The walk on top of the wall in front of the tower (pixel y), if the tower reaches it."""
        w = game.world
        gy = self.ground(game)
        y = gy - 4
        while y > gy - self.h - 20 and w.solid_point(wx, y):
            y -= 4
        if gy - y > self.h - 8:
            return None
        return y + 2

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
            px = gh.port_x
            d = (px - self.x) * self.facing
            if rng_min < d < rng_max and (best is None or d < best[0] * 1.6):
                best = (d, px + self.facing * random.choice((0, 16, 40)), gh.hinge[1] - random.randint(3, 9) * TILE)
        # any hostile wall in range
        if best is None:
            for s in game.world.settlements:
                si = game.world.settlements.index(s)
                owner = "bandit" if s["type"] == "robber" else game.society.owner.get(si, s["kingdom"])
                if not game.hostile_factions(self.side, owner):
                    continue
                for r in s["buildings"]:
                    if r["kind"] in ("wall", "gatehouse", "tower", "keep"):
                        px = (r["x0"] + 1) * TILE
                        d = (px - self.x) * self.facing
                        if rng_min < d < rng_max and (best is None or d < best[0]):
                            best = (d, px, r["g"] * TILE - random.randint(2, 8) * TILE)
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
    hf.ramp_t = 0.45 / max(1, min(3, len(hf.front)))
    f = hf.facing
    i = int((hf.x + f * 10) // TILE)
    # raise the ground under the front a little, sloping back toward the formation
    for k in range(0, 5):
        col = i - f * k
        if 0 <= col < w.w:
            target = w.top[col] - (5 - k) * 2.5
            w.top[col] = max(target, w.top[col] - 6)
    lo, hi = min(i, i - f * 5), max(i, i - f * 5)
    w.set_surface(lo, hi + 1, w.top[lo:hi + 1].copy())
    for wr in w.water:
        if wr.x0 <= hf.x <= wr.x1 and not wr.lava and wr.x1 - wr.x0 < 200:
            # the moat fills with earth: its water level effectively drops under the ramp
            pass
    game.fx.dust(hf.x + f * 10, hf.ground(hf.x), 3, (112, 78, 52))
    hf.y_cache.clear()
    if random.random() < 0.12:
        hf.shout = ["[Rampe aufschütten|build up the ramp]!", 1.5]


def ladder(game, hf, blocked, dt):
    """Sturmleitern: raise a ladder against the wall, then climb it one man at a time."""
    w = game.world
    f = hf.facing
    lad = getattr(hf, "ladder", None)
    wx = blocked.bb[0] if f > 0 else blocked.bb[2]
    gy = hf.ground(hf.x)
    if lad is None or abs(lad.get("wx", 0) - wx) > 20 or lad.get("obj") is not None and lad["obj"].removed:
        # how tall is the wall here?
        y = gy - 8
        while y > gy - 20 * TILE and w.solid_point(wx + f * 3, y):
            y -= 4
        height = gy - y
        if height > 15 * TILE:
            return False
        hf.ladder = lad = {"wx": wx, "x": wx - f * 10, "top": y, "t": 2.5, "up": False, "climb": 0.0, "obj": None}
        hf.shout = ["[Leitern an die Mauer|ladders to the wall]!", 2.0]
    if not lad["up"]:
        lad["t"] -= dt
        if lad["t"] <= 0:
            lad["up"] = True
            L = gy - lad["top"] + 10
            pts = [(-6, -L / 2), (6, -L / 2), (6, L / 2), (-6, L / 2)]
            o = PhysObject.spawn(w, pts, lad["x"], gy - L / 2, "timber", "crafted", item="ladder",
                                 shape_key="ladder", angle=f * 0.12)
            o.anchor(True)
            game.on_anchor(o)
            lad["obj"] = o
            game.ladders.append({"obj": o, "x": lad["x"], "top": lad["top"], "bottom": gy, "side": hf.side, "t": 0.0,
                                 "hf": hf})
            game.sfx("place")
        return True
    o = lad["obj"]
    if o is None or o.removed or not o.anchored:      # pushed away — raise it again
        hf.ladder = None
        return True
    lad["climb"] -= dt
    if lad["climb"] <= 0 and hf.members:
        lad["climb"] = 1.3
        h = spawn_assault_fighter(game, hf, lad["x"], gy)
        if h is not None:
            game.set_brain(h, "climb")
            h.climb_target = (lad["x"], lad["top"], lad["wx"])
    return True


def sap(game, hf, blocked, dt):
    """Mineure: dig under the wall, hold it up on timber props, then burn the props."""
    from shapely.geometry import box
    w = game.world
    f = hf.facing
    job = getattr(hf, "sap", None)
    if job is not None and job["lit"] and (blocked is None or abs(job["wx"] - blocked.cx) > 30):
        job = None                       # that wall is down: start on the next one
    if job is None:
        b = PF.building(w, blocked.bld)
        if b is None:
            return False
        gy = hf.ground(hf.x)
        x_in = blocked.bb[0] - 3 * TILE if f > 0 else blocked.bb[2] + 3 * TILE
        x_end = (b.x1 + 8) if f > 0 else (b.x0 - 8)
        hf.sap = job = {"x": x_in, "end": x_end, "gy": gy, "t": 0.0, "lit": False, "fuse": 4.0, "wx": blocked.cx,
                        "bld": b.id, "props": [], "step": 0}
        hf.shout = ["[Untergraben|undermine]!", 2.0]
    if not job.get("dug"):
        job["t"] -= dt
        if job["t"] > 0:
            return True
        job["t"] = 0.5
        x0 = job["x"]
        x1 = x0 + f * 16
        gy = job["gy"]
        # the shaft goes down at first, then runs level under the wall
        depth = min(3, job["step"]) * 12 + 14
        tunnel = box(min(x0, x1) - 1, gy + depth - 30, max(x0, x1) + 1, gy + depth + 6)
        w.add_cave(tunnel)
        game.fx.dust(x0, gy + depth, 3, (112, 78, 52))
        if job["step"] % 5 == 0:
            game.sfx("dig")
        job["step"] += 1
        job["x"] = x1
        # under the wall: take the foundation out and set a timber prop in its place
        bld = PF.building(w, job["bld"])
        if bld is not None and bld.x0 - 8 <= x1 <= bld.x1 + 8:
            for pid in list(bld.pieces):
                pc = w.pieces.get(pid)
                if pc is not None and pc.grounded and pc.solid and pc.bb[0] <= x1 + 8 and pc.bb[2] >= x1 - 8:
                    pc.grounded = False
            B = PF.Builder(w, "props", "wood")
            prop = B.rect(x1 - 4, gy + depth - 30, x1 + 4, gy + 4, "timber", "prop", detail="grain")
            B.finish(None)
            prop.grounded = True
            prop.bld_target = job["bld"]
            bld.pieces.append(prop.id)
            bld2 = PF.building(w, prop.bld)
            if bld2 is not None and prop.id in bld2.pieces:
                bld2.pieces.remove(prop.id)
            prop.bld = job["bld"]
            for pid in bld.pieces:
                pc = w.pieces.get(pid)
                if pc is not None and pc.solid and pc.bb[0] <= x1 + 10 and pc.bb[2] >= x1 - 10 and pc.id != prop.id:
                    if pc.bb[3] >= gy - 3:
                        pc.below.append(prop.id)
            job["props"].append(prop.id)
        if (job["x"] - job["end"]) * f > 0:
            job["dug"] = True
        return True
    if not job["lit"]:
        job["fuse"] -= dt
        if job["fuse"] <= 0:
            job["lit"] = True
            for pid in job["props"]:
                pc = w.pieces.get(pid)
                if pc is not None:
                    game.ignite_piece(pc)
            hf.shout = ["[Feuer an die Stützen|fire the props]!", 2.5]
            game.fx.text(job["x"], job["gy"] - 60, "Die Stützen brennen!", (255, 170, 100),
                         gloss="the props are burning!")
    return True


def update(game, dt):
    """Defender reflexes: raise drawbridges, drop portcullises, pour pitch, push ladders away."""
    w = game.world
    px = game.player.cx
    for gh in w.gatehouses:
        gx = gh.hinge[0]
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
        if not gh.auto:
            continue
        if threat is not None:
            gh.calm = 0.0
            if not gh.closed:
                set_defenses(game, gh, True)
                game.fx.text(gx, gh.hinge[1] - 16 * TILE, "Zugbrücke hoch!", (255, 220, 150),
                             gloss="raise the drawbridge!")
            gh.pitch_t -= dt
            mx = gh.pechnase[0]
            near_gate = any(not e.dead and abs(e.x - mx) < e.w / 2 + 24 and game.hostile_factions(owner, e.side)
                            for e in game.engines)
            near_gate = near_gate or any(not hf.dead and hf.span()[0] - 24 <= mx <= hf.span()[1] + 24 and
                                         game.hostile_factions(owner, hf.side) for hf in game.formations)
            if near_gate and gh.pitch_t <= 0 and gh.pitch > 0:
                gh.pitch_t = 7.0
                gh.pitch -= 1
                pour_pitch(game, gh)
        else:
            gh.calm += dt
            if gh.closed and gh.calm > 15:
                set_defenses(game, gh, False)
    # ladders: a defender at the top shoves them off
    for lad in list(game.ladders):
        o = lad.get("obj")
        if o is None or o.removed or not o.anchored:
            game.ladders.remove(lad)
            continue
        lx, ly = lad["x"], lad["top"]
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
            r = getattr(o, "ladder_rect", None)
            if r is not None:
                w.remove_ladder(r)
            o.anchor(False)
            if o.body is not None:
                f = lad["hf"].facing if lad.get("hf") else 1
                o.body.apply_impulse_at_local_point((-f * o.mass() * 160, 0), (0, -40))
            defender.say("[Leiter weg|away with the ladder]!", t=2)
            game.hear("[Leiter weg|away with the ladder]!", "siege")
            for h in game.humanoids:
                if abs(h.cx - lx) < 16 and ly < h.feet < lad["bottom"] + 4:
                    h.climbing = False
                    h.vx = -lad["hf"].facing * 120 if lad.get("hf") else 0
            game.ladders.remove(lad)
    # assaulters who hold the wall open the gate
    alive = [h for h in game.assaulters if not h.dead and not h.removed]
    game.assaulters = alive
    for gh in w.gatehouses:
        if not gh.closed and not gh.forced:
            continue
        gx = gh.port_x
        near = [h for h in alive if abs(h.cx - gx) < 260 and game.hostile_factions(h.faction,
                                                                                    gatehouse_owner(game, gh) or "")]
        if len(near) >= 3:
            gh.held += dt
            if gh.held > 8 and not gh.forced:
                gh.forced = True
                gh.auto = False
                set_defenses(game, gh, False)
                for pid in w.near("piece_chunks", gx - 60, gx + 60):
                    pc = w.pieces.get(pid)
                    if pc is not None and pc.role == "door":
                        PF.toggle_door(w, pc, True)
                        pc.locked = False
                game.fx.text(gx, gh.hinge[1] - 14 * TILE, "Das Tor ist offen!", (255, 230, 140),
                             gloss="the gate is open!")
                game.sfx("horn")
        else:
            gh.held = 0.0


def impact(game, x, y, kind):
    """A trebuchet stone or a powder ball strikes the world: pieces near the impact take the blow."""
    w = game.world
    r = 30 if kind == "stone" else 20
    power = 30.0 if kind == "stone" else 45.0
    hit = []
    for pid in list(w.near("piece_chunks", x - r - 40, x + r + 40)):
        pc = w.pieces.get(pid)
        if pc is None or not pc.solid or pc.state != "static":
            continue
        d = math.hypot(pc.cx - x, pc.cy - y) - max(pc.w, pc.h) / 2
        if d < r:
            hit.append((d, pc))
    hit.sort(key=lambda t: t[0])
    for d, pc in hit[:6]:
        f = max(0.2, 1.0 - max(0.0, d) / r)
        game.damage_piece(pc, power * f / max(0.5, MATS[pc.mat].hard) * 2.0,
                          impulse=((pc.cx - x) * 20, (pc.cy - y) * 20))
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
    # the stone itself stays where it fell
    if kind == "stone":
        pts = [(-7, -5), (-2, -8), (6, -6), (8, 2), (1, 7), (-6, 5)]
        PhysObject.spawn(w, pts, x, y - 10, "rock", "debris", debris=True, item="stone")
