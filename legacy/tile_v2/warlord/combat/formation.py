"""Der Haufen — the formation as a single entity.

A 2D side view can't show armies spread across a field, so a Haufen *compresses* a block of
soldiers into one entity drawn in several depth ranks (pseudo-3D). Only the front rank is made
of real, individually simulated fighters who duel the enemy front. Everyone behind is an abstract
member record that:
  * steps forward when a front fighter falls (the line holds while bodies remain),
  * rotates in on 'Wechsel!' so wounded men rest (your original rotation idea),
  * adds pressure (push of pike), extra reach (pike ranks 2-3), and morale,
  * can be shot by volleys, trampled by a charge, or cut down from behind (flanking).
"""
import math
import random

import pygame

from ..settings import TILE, WALK_SPEED, RUN_SPEED, HORSE_GALLOP
from ..world import tiles as T
from ..society.names import make_look
from ..gfx.sprites import soldier_sprite, FX as SFX, FY as SFY
from .units import UNITS

STANCES = {
    #            spacing push  arrow_mult speed  melee_def
    "normal": (11, 1.0, 1.0, 1.0, 1.0),
    "schildwall": (8, 1.25, 0.25, 0.55, 1.3),
    "igel": (8, 1.1, 0.9, 0.0, 1.1),
    "keil": (9, 1.5, 1.1, 1.1, 0.8),
    "locker": (17, 0.6, 0.45, 1.15, 0.7),
}


class Haufen:
    _ids = 0

    def __init__(self, game, side, unit_key, count, x, facing, colors=None, name=None, leader=None):
        Haufen._ids += 1
        self.id = Haufen._ids
        self.game = game
        self.side = side
        self.unit = UNITS[unit_key]
        self.colors = colors or ((120, 120, 120), (220, 220, 220))
        rng = game.rng
        self.protos = []
        for i in range(3):
            look = make_look(rng, 1 if self.unit.quality < 0.5 else 3, soldier=True, kingdom_colors=self.colors)
            look["hat"] = None if self.unit.helmet else look.get("hat")
            from ..entities.humanoid import Humanoid
            p = Humanoid(0, 0, look, side, "proto")
            p.equip(weapon=self.unit.weapons[i % len(self.unit.weapons)], shield=self.unit.shield or "",
                    armor=self.unit.armor, helmet=self.unit.helmet or "")
            p.weapon_drawn = True
            self.protos.append(p)
        self.members = [{"hp": 100.0, "proto": i % 3, "fatigue": 0.0} for i in range(count)]
        self.initial = count
        self.front = []
        self.front_size = 2 if not self.unit.cavalry else 2
        self.x = float(x)          # px, the leading edge
        self.facing = facing
        self.order = "halt"
        self.stance = "normal"
        self.morale = 55 + self.unit.quality * 45
        self.routed = False
        self.dead = False
        self.speed = 0.0
        self.name = name or f"{self.unit.de}"
        self.leader = leader
        self.contact = None
        self.blocked_by_tile = None
        self.volley_t = random.uniform(1, 3)
        self.spawn_delay = 0.0
        self.walk_phase = 0.0
        self.push_t = 0.0
        self.anim_t = 0.0
        self.charge_cool = 0.0
        self.selected = False
        self.flank_t = 0.0
        self.y_cache = {}
        self.base_row = None
        self.last_casualty = 0.0
        self.recent_losses = 0
        self.follow_target = None
        self.shout = None
        self.target = None
        self.engaged = False

    # ------------------------------------------------------------- geometry
    @property
    def count(self):
        return len(self.members) + len([f for f in self.front if not f.dead])

    def spacing(self):
        return STANCES[self.stance][0] * (1.6 if self.unit.cavalry else 1.0)

    def rows(self):
        return 3

    def width(self):
        cols = math.ceil(len(self.members) / self.rows()) + 1
        return cols * self.spacing() + 20

    def back_x(self):
        return self.x - self.facing * self.width()

    def span(self):
        a, b = self.x, self.back_x()
        return (min(a, b), max(a, b))

    def ground(self, px):
        """Ground under column px at *our* level: we can climb a few tiles, but never onto a wall-top arch."""
        w = self.game.world
        tx = max(0, min(w.w - 1, int(px // TILE)))
        if self.base_row is None:
            ref = int(w.surface[tx]) - 30
            self.base_row = w.ground_at(tx, max(0, ref))
        key = (tx, self.base_row)
        g = self.y_cache.get(key)
        if g is None:
            row = w.ground_at(tx, max(0, self.base_row - 3))
            if row < self.base_row - 2 or (row > 0 and T.SOLID[w.fg[tx, row - 1]]):
                row = self.base_row          # a wall column: stand at our own level
            g = row * TILE
            self.y_cache[key] = g
            if len(self.y_cache) > 600:
                self.y_cache.clear()
        return g

    def track_ground(self):
        w = self.game.world
        tx = max(0, min(w.w - 1, int(self.x // TILE)))
        if self.base_row is None:
            self.ground(self.x)
        nb = w.ground_at(tx, max(0, self.base_row - 3))
        # only follow walkable ground: a step of up to 2 tiles with headroom, or any drop
        if nb < w.h and (nb >= self.base_row - 2) and not T.SOLID[w.fg[tx, nb - 1]]:
            self.base_row = nb

    def contains(self, px, py):
        a, b = self.span()
        if not (a <= px <= b):
            return False
        gy = self.ground(px)
        h = 60 if self.unit.cavalry else 46
        return gy - h <= py <= gy + 2

    def rect(self):
        a, b = self.span()
        gy = self.ground((a + b) / 2)
        return (a, gy - 46, b - a, 46)

    def center(self):
        a, b = self.span()
        return ((a + b) / 2, self.ground((a + b) / 2) - 24)

    # ------------------------------------------------------------- front fighters
    def _spawn_front(self, slot):
        if not self.members:
            return None
        m = self.members.pop(0)
        proto = self.protos[m["proto"]]
        from ..entities.humanoid import Humanoid
        g = self.game
        fx = self.x - self.facing * (slot * 16 + 8)
        gy = self.ground(fx)
        h = Humanoid(fx - 7, gy - 42, dict(proto.look), self.side, proto.name)
        h.equip(weapon=proto.weapon_key, shield=self.unit.shield or "", armor=self.unit.armor,
                helmet=self.unit.helmet or "")
        h.hp = m["hp"]
        h.facing = self.facing
        h.formation = self
        h.skill = 0.35 + self.unit.quality * 0.5
        h.weapon_drawn = True
        h.name = self.unit.de
        h.slot = slot
        if self.unit.cavalry:
            horse = g.spawn_horse(fx, gy, wild=False)
            horse.owner = h
            g.mount(h, horse)
        g.add_humanoid(h, brain="formation")
        return h

    def _retire_front(self, h):
        """Rotation: a tired front fighter steps back into the block."""
        self.members.append({"hp": h.hp, "proto": 0, "fatigue": 0.0})
        if h.mount is not None:
            self.game.remove_entity(h.mount)
        h.removed = True
        self.front.remove(h)

    def rotate(self):
        for h in list(self.front):
            if not h.dead and len(self.members) > 0 and h.hp < 85:
                self._retire_front(h)
        self.spawn_delay = 0.25
        self.shout_text("wechsel")

    # ------------------------------------------------------------- orders
    def set_order(self, order, shout=True):
        if order in STANCES:
            self.stance = order
            for f in self.front:
                f.formation_stance = order
        elif order == "wechsel":
            self.rotate()
            return
        else:
            self.order = order
            if order == "halt" and self.routed and self.morale > 25:
                self.routed = False
        if shout:
            self.shout_text(order)

    def shout_text(self, order):
        from ..society.dialogue import ORDERS
        if order in ORDERS:
            self.shout = [ORDERS[order][0], 2.0]
            if self.side == "player":
                self.game.hear(ORDERS[order][0], "orders")

    # ------------------------------------------------------------- update
    def enemies(self):
        g = self.game
        return [h for h in g.formations if not h.dead and h is not self and g.hostile_factions(self.side, h.side)]

    def nearest_enemy(self):
        best, bd = None, 1e9
        for e in self.enemies():
            d = abs(e.x - self.x)
            if d < bd:
                best, bd = e, d
        return best, bd

    def update(self, dt):
        g = self.game
        self.anim_t += dt
        if self.shout:
            self.shout[1] -= dt
            if self.shout[1] <= 0:
                self.shout = None
        self.front = [f for f in self.front if not f.removed]
        # casualties at the front
        for f in list(self.front):
            if f.dead:
                self.front.remove(f)
                f.formation = None
                self._casualty()
        # fill front slots
        if self.spawn_delay > 0:
            self.spawn_delay -= dt
        elif len(self.front) < self.front_size and self.members and not self.routed:
            used = {getattr(f, "slot", 0) for f in self.front}
            slot = next(i for i in range(self.front_size + 1) if i not in used)
            h = self._spawn_front(slot)
            if h:
                self.front.append(h)
            self.spawn_delay = 0.55
        if self.count <= 0:
            self.dead = True
            return
        # rest heals reserve
        for m in self.members:
            if m["hp"] < 100:
                m["hp"] = min(100.0, m["hp"] + 3 * dt)
        # auto-rotation for good troops
        if self.unit.quality >= 0.55 and self.members:
            for f in list(self.front):
                if not f.dead and f.hp < 30 and f.stagger <= 0 and random.random() < dt * 1.5:
                    self._retire_front(f)
                    self.spawn_delay = 0.2
        self.track_ground()
        enemy, dist = self.nearest_enemy()
        self.target = enemy
        # morale
        if self.engaged or self.recent_losses:
            pass
        else:
            self.morale = min(100, self.morale + 1.5 * dt)
        self.recent_losses = max(0, self.recent_losses - dt * 0.5)
        if self.leader is not None and not getattr(self.leader, "dead", False):
            if abs(self.leader.cx - self.center()[0]) < 260:
                self.morale = min(100, self.morale + 1.2 * dt)
        if self.morale <= 12 and not self.routed:
            self.routed = True
            self.order = "flucht"
            g.fx.text(self.center()[0], self.center()[1] - 50, "Flucht!", (255, 120, 90), gloss="they flee!")
            g.on_rout(self)
        # movement
        self._move(dt, enemy, dist)
        # volleys
        if self.unit.ranged and not self.routed:
            self._volley(dt, enemy, dist)
        # clash pressure
        self._clash(dt, enemy, dist)
        # front fighters keep their slots
        for f in self.front:
            f.formation_stance = self.stance
        # routed soldiers desert
        if self.routed:
            if self.members and random.random() < dt * 1.2:
                self.members.pop()
            if not self.members:
                for f in self.front:
                    f.formation = None
                    g.set_brain(f, "flee")
                self.front = []
                self.dead = True

    def _move(self, dt, enemy, dist):
        g = self.game
        st = STANCES[self.stance]
        base = WALK_SPEED * 0.75
        if self.unit.cavalry:
            base = 120
        want = 0.0
        if self.order == "vorwaerts":
            want = base * st[3]
        elif self.order == "angriff":
            want = (RUN_SPEED * 0.9 if not self.unit.cavalry else HORSE_GALLOP * 0.95) * max(0.5, st[3])
        elif self.order == "zurueck":
            want = -base * 0.8
        elif self.order == "flucht":
            want = -RUN_SPEED
        elif self.order == "folgt" and self.leader is not None:
            d = (self.leader.cx - self.x) * self.facing
            target_off = 50
            if abs(self.leader.cx - self.x) > 80:
                self.facing = 1 if self.leader.cx > self.x - self.facing * self.width() / 2 else -1
            want = base * 1.4 if d > target_off else 0.0
        # turn to face the enemy when halted / advancing
        if enemy is not None and self.order in ("halt", "vorwaerts", "angriff") and dist < 900:
            want_face = 1 if enemy.center()[0] > self.center()[0] else -1
            if want_face != self.facing and self.contact is None:
                # wheel around: the block pivots on its centre
                c = self.center()[0]
                self.facing = want_face
                self.x = c + self.facing * self.width() / 2
        if self.order == "flucht" and enemy is not None:
            away = 1 if self.center()[0] > enemy.center()[0] else -1
            if away != -self.facing * 1 and self.facing != -away:
                pass
            want = RUN_SPEED * 1.0
            if self.facing != away:
                c = self.center()[0]
                self.facing = away
                self.x = c + self.facing * self.width() / 2
        # contact stops movement
        if self.contact is not None and want > 0 and self.order != "flucht":
            want = 0.0
        # don't march through friendly formations: queue up behind them
        if want > 0 and self.order not in ("flucht",):
            for f in g.formations:
                if f is self or f.dead or f.side != self.side or f.facing != self.facing:
                    continue
                fa, fb = f.span()
                back = fa if self.facing > 0 else fb
                gap = (back - self.x) * self.facing
                stuck_ahead = f.contact is not None or f.blocked_by_tile is not None
                if stuck_ahead and -10 < gap < 24 and (f.center()[0] - self.center()[0]) * self.facing > 0:
                    want = min(want, max(0.0, f.speed))
                    break
        # cavalry charge gets the full gallop only after a run-up
        if self.unit.cavalry and self.order == "angriff":
            self.speed += (want - self.speed) * min(1.0, dt * 1.2)
        else:
            self.speed += (want - self.speed) * min(1.0, dt * 4)
        if abs(self.speed) < 1:
            self.speed = 0.0
        if self.speed == 0:
            return
        dx = self.facing * self.speed * dt
        wtx = int(self.x // TILE)
        wty = int(self.ground(self.x) // TILE) - 1
        if g.world.inside(wtx, wty) and g.world.liq[wtx, wty] > 2:
            dx *= 0.45   # wading
        # obstacles: a wall or gate in the way
        lead = self.x + self.facing * 6 + dx
        tx = int(lead // TILE)
        gy = self.ground(self.x)
        ty_feet = int(gy // TILE) - 1
        w = g.world
        blocked_tile = None
        for ty in range(ty_feet - 2, ty_feet + 1):
            if w.inside(tx, ty) and T.SOLID[w.fg[tx, ty]]:
                # a single step is fine
                if ty == ty_feet and not (w.inside(tx, ty - 1) and T.SOLID[w.fg[tx, ty - 1]]):
                    continue
                blocked_tile = (tx, ty)
                break
        if blocked_tile and self.speed > 0:
            self.blocked_by_tile = blocked_tile
            self.speed = 0
            if self.order in ("vorwaerts", "angriff") and self.front:
                from . import siege
                tid = int(w.fg[blocked_tile])
                if not T.BUILT[tid]:
                    siege.ramp(g, self, dt)          # a bank or a cliff: shovel a ramp
                    return
                if self.unit.key == "leiter" and siege.ladder(g, self, blocked_tile, dt):
                    return
                if self.unit.key == "mineure" and siege.sap(g, self, blocked_tile, dt):
                    return
            # siege: the front ranks hack at the gate / wall in their way
            if self.order == "angriff" and self.front:
                tid = int(w.fg[blocked_tile])
                if T.TILES[tid].hardness < 999:
                    power = 0.9 * len([f for f in self.front if not f.dead]) * (1.6 if tid in (T.GATE.id,
                                                                                               T.DOOR.id) else 1.0)
                    if g.damage_tile(blocked_tile[0], blocked_tile[1], power * dt, None) and \
                            random.random() < 0.3:
                        g.fx.text(blocked_tile[0] * TILE, blocked_tile[1] * TILE - 20, "Bresche!",
                                  (255, 200, 120), gloss="breach!")
            return
        self.blocked_by_tile = None
        self.x += dx
        self.walk_phase += abs(dx) * 0.15

    def _volley(self, dt, enemy, dist):
        g = self.game
        self.volley_t -= dt
        rng_px = 760 if self.unit.ranged == "arrow" else 620
        tgt = None
        if enemy is not None and dist < rng_px:
            tgt = enemy.center()
        else:
            # individuals (e.g. the player) in range
            best = None
            for h in g.humanoids:
                if h.dead or not g.hostile_factions(self.side, h.faction):
                    continue
                d = abs(h.cx - self.x)
                if d < rng_px * 0.8 and (best is None or d < best[0]):
                    best = (d, (h.cx, h.y + 16))
            if best:
                tgt = best[1]
        if tgt is None or self.volley_t > 0 or self.contact is not None:
            return
        if self.order not in ("halt", "salve", "vorwaerts") and self.order != "salve":
            return
        self.volley_t = (4.2 if self.unit.ranged == "arrow" else 7.5) * random.uniform(0.9, 1.1)
        n = min(len(self.members) + len(self.front), 22)
        a, b = self.span()
        kind = self.unit.ranged
        for i in range(n):
            sx = random.uniform(a, b)
            sy = self.ground(sx) - 34
            g.fire_volley_arrow(self, sx, sy, tgt[0] + random.uniform(-40, 40), tgt[1], kind)
        self.shout_text("salve")
        g.sfx("volley")

    def _clash(self, dt, enemy, dist):
        g = self.game
        self.contact = None
        self.engaged = False
        if enemy is None:
            return
        # distance between our front edge and their front edge
        ea, eb = enemy.span()
        gap = (ea - self.x) if self.facing > 0 else (self.x - eb)
        if gap < 26 and gap > -60 and (enemy.center()[0] - self.center()[0]) * self.facing > 0:
            self.contact = enemy
            self.engaged = True
            # cavalry impact
            if self.unit.cavalry and self.speed > 140 and self.charge_cool <= 0:
                self._impact(enemy)
            # push of pike
            self.push_t -= dt
            if self.push_t <= 0:
                self.push_t = 0.6
                mine = self.pressure()
                theirs = enemy.pressure()
                ratio = mine / max(0.5, theirs)
                if mine > theirs * 1.25:
                    shove = min(10.0, (ratio - 1) * 6)
                    enemy.x += self.facing * shove
                    enemy.morale -= 0.8
                # the press of bodies: men fall in the ranks behind the duelling front
                kill_p = 0.16 * min(2.5, ratio) ** 0.8 * (0.5 + self.unit.quality) * STANCES[enemy.stance][4] ** -1
                if random.random() < kill_p:
                    enemy._kill_member(enemy.x - enemy.facing * random.uniform(10, 40))
                # pike ranks reach past the front
                if "polearm" in self.protos[0].weapon_def.flags and enemy.front and len(self.members) >= 3:
                    victim = random.choice(enemy.front)
                    if not victim.dead and random.random() < 0.35:
                        attacker = self.front[0] if self.front else None
                        if attacker is not None:
                            victim.take_hit(g, attacker, self.protos[0].weapon_def.dmg * 0.5, "pierce", 10,
                                            high=False, source_x=self.x)
        if self.charge_cool > 0:
            self.charge_cool -= dt
        # cavalry wheel away after a charge
        if self.unit.cavalry and self.order == "angriff" and self.contact is not None and self.charge_cool > 2.0:
            self.order = "zurueck"
            self._wende_t = 1.6
        if getattr(self, "_wende_t", 0) > 0:
            self._wende_t -= dt
            if self._wende_t <= 0 and self.order == "zurueck":
                self.order = "angriff"

    def _impact(self, enemy):
        g = self.game
        self.charge_cool = 4.0
        speed_f = self.speed / HORSE_GALLOP
        n = len(self.members) + len(self.front)
        braced = enemy.stance == "igel" and "brace" in enemy.protos[0].weapon_def.flags
        cx, cy = enemy.x, enemy.ground(enemy.x) - 30
        if braced:
            losses = int(max(1, n * 0.35 * speed_f))
            for _ in range(losses):
                self._kill_member()
            self.morale -= 30
            g.fx.text(cx, cy - 30, "Der Igel hält!", (255, 210, 120), gloss="the hedgehog holds!")
            g.fx.sparks(cx, cy, 30)
            self.speed = -60
        else:
            kills = int(max(1, n * 0.45 * speed_f * (0.6 if enemy.stance == "schildwall" else 1.0)))
            for _ in range(kills):
                enemy._kill_member()
            enemy.morale -= 22 * speed_f
            enemy.x += self.facing * 24
            g.fx.text(cx, cy - 30, "Ansturm!", (255, 160, 90), gloss="charge!")
            g.fx.blood(cx, cy, 30, self.facing)
            for f in enemy.front:
                f.vx += self.facing * 220
                f.stagger = max(f.stagger, 0.8)
        g.camera.shake = max(g.camera.shake, 7)
        g.sfx("impact")

    def pressure(self):
        st = STANCES[self.stance]
        depth = len(self.members)
        q = self.unit.quality
        living_front = sum(1 for f in self.front if not f.dead)
        return (living_front * 3 + math.sqrt(depth) * 2.0) * (0.5 + q) * st[1] * (0.35 + self.morale / 100)

    # ------------------------------------------------------------- damage to the abstract block
    def _casualty(self):
        self.morale -= 120.0 / max(10, self.initial) + 1.2
        self.recent_losses += 1
        self.last_casualty = self.anim_t

    def _kill_member(self, x=None):
        if self.members:
            self.members.pop(random.randrange(len(self.members)))
            self._casualty()
            c = self.center()
            px = x if x is not None else random.uniform(*self.span())
            self.game.add_corpse_sprite(self, px, self.ground(px))
            return True
        if self.front:
            f = random.choice(self.front)
            if not f.dead:
                f.die(self.game, None)
                return True
        return False

    def arrow_hit(self, g, p):
        st = STANCES[self.stance]
        from_front = (p.vx * self.facing) < 0
        mult = st[2] if from_front or self.stance == "locker" else 1.0
        if self.stance == "schildwall" and p.vy > 250:
            mult = max(mult, 0.6)   # plunging arrows over the shields
        armor = {"kleidung": 1.0, "gambeson": 0.75, "kettenhemd": 0.5, "plattenrock": 0.28}[self.unit.armor]
        if p.kind == "bolt":
            armor = min(1.0, armor * 1.8)
        if self.unit.cavalry:
            mult *= 1.3   # horses are big targets
        chance = 0.4 * mult * armor
        self.morale -= 0.25
        if random.random() < chance:
            if self.members:
                m = random.choice(self.members)
                m["hp"] -= p.dmg * 2.2
                if m["hp"] <= 0:
                    self.members.remove(m)
                    self._casualty()
                    self.game.add_corpse_sprite(self, p.x, self.ground(p.x))
                else:
                    self.game.fx.blood(p.x, p.y, 4)
            return True
        if self.stance == "schildwall" and from_front:
            self.game.fx.dust(p.x, p.y, 1, (150, 120, 90))
            return True
        return random.random() < 0.6

    def melee_hit(self, att, dmg, px):
        """Someone is hacking into the block from the side/rear (flanking)."""
        rear = (att.cx - self.center()[0]) * self.facing < 0
        if random.random() < (0.55 if rear else 0.25):
            self._kill_member(px)
        self.morale -= 2.5 if rear else 1.0
        if rear:
            self.flank_t = 1.0

    # ------------------------------------------------------------- drawing
    def draw(self, surf, ox, oy, font):
        a, b = self.span()
        if b < ox - 100 or a > ox + surf.get_width() + 100:
            return
        sp = self.spacing()
        rows = self.rows()
        n = len(self.members)
        moving = abs(self.speed) > 5
        state = "walk" if moving else "idle"
        if self.routed:
            state = "run"
        frame = int(self.walk_phase * 1.2) % 8 if moving else 0
        action = None
        if self.stance in ("schildwall",) and self.unit.shield:
            action = "block"
        if self.engaged and int(self.anim_t * 3) % 2 == 0:
            action = "attack" if not self.unit.ranged else action
        if self.unit.ranged and self.volley_t > 3.2 and not self.engaged:
            action = "bow" if self.unit.ranged == "arrow" else None
        facing = self.facing if not self.routed else self.facing
        # draw back rows first (higher on screen, darker), front row last
        for r in range(rows - 1, -1, -1):
            shade = 1.0 - r * 0.17
            for i in range(r, n, rows):
                col = i // rows + 1
                px = self.x - self.facing * (col * sp + 10) + self.facing * r * 3
                gy = self.ground(px)
                m = self.members[i]
                proto = self.protos[m["proto"]]
                fr = (frame + i * 3) % 8 if moving else 0
                if self.unit.cavalry:
                    self._draw_rider(surf, px - ox, gy - oy - r * 5, proto, fr, shade, moving)
                    continue
                s = soldier_sprite(proto, state, fr, facing, shade, action if (i // rows) < 2 or action == "block"
                                   else (action if action == "bow" else None))
                surf.blit(s, (px - ox - SFX, gy - oy - SFY - r * 5))
        # banner
        bx = self.x - self.facing * (self.width() * 0.5)
        gy = self.ground(bx)
        top = gy - oy - 86
        pygame.draw.line(surf, (90, 70, 40), (bx - ox, gy - oy - 30), (bx - ox, top), 2)
        c1, c2 = self.colors
        flutter = math.sin(self.anim_t * 5) * 2
        pts = [(bx - ox, top), (bx - ox + 20 * self.facing, top + 3 + flutter), (bx - ox, top + 14)]
        pygame.draw.polygon(surf, c1, pts)
        pygame.draw.circle(surf, c2, (int(bx - ox + 6 * self.facing), int(top + 7)), 2)
        # label + morale bar
        label = f"{self.unit.de} ({self.count})"
        if self.stance != "normal":
            label += f" · {self.stance.capitalize()}"
        col = (255, 240, 180) if self.selected else (230, 230, 230)
        if self.routed:
            col = (255, 120, 100)
        img = font.render(label, True, col)
        surf.blit(img, (bx - ox - img.get_width() / 2, top - 30))
        mw = 60
        pygame.draw.rect(surf, (30, 30, 30), (bx - ox - mw / 2, top - 12, mw, 4))
        mc = (90, 200, 90) if self.morale > 50 else (230, 190, 60) if self.morale > 25 else (220, 70, 60)
        pygame.draw.rect(surf, mc, (bx - ox - mw / 2, top - 12, mw * max(0, self.morale) / 100, 4))
        if self.selected:
            pygame.draw.rect(surf, (255, 230, 140), (a - ox - 4, gy - oy - 70, b - a + 8, 74), 1, border_radius=4)
        if self.shout:
            from ..society.dialogue import plain
            t = font.render(plain(self.shout[0]), True, (255, 230, 140))
            surf.blit(t, (self.x - ox - t.get_width() / 2, gy - oy - 110))

    def _draw_rider(self, surf, x, y, proto, frame, shade, moving):
        from ..entities.animals import draw_horse_simple
        draw_horse_simple(surf, x, y, self.facing, frame, shade, moving)
        s = soldier_sprite(proto, "ride", frame, self.facing, shade, None)
        surf.blit(s, (x - SFX, y - SFY - 18))
