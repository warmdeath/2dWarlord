"""NPC brains. A brain looks at the world and fills in the humanoid's Intent — nothing more.

LifeBrain       daily schedule by occupation (sleep, work, eat, pray, gossip) with real effects on the
                world: farmers harvest and re-sow, woodcutters fell trees, villagers fight fires.
CombatBrain     approach, feint, block on the enemy's wind-up, parry if skilled, retreat when hurt.
FormationBrain  front-rank fighter of a Haufen: holds its slot, fights what's in reach.
FollowerBrain   your retinue: follows you and fights your enemies.
FleeBrain       run for it.
"""
import math
import random

from ..settings import TILE, DAY_LENGTH
from ..world import tiles as T
from ..society import dialogue as D


def walk_to(h, game, tx_px, run=False, tol=6):
    it = h.intent
    d = tx_px - h.cx
    if abs(d) <= tol:
        it.mx = 0
        return True
    it.mx = 1 if d > 0 else -1
    it.run = run
    w = game.world
    # open doors in the way
    fx = int((h.cx + it.mx * (h.w / 2 + 4)) // TILE)
    for ty in (int((h.feet - 8) // TILE), int((h.feet - 24) // TILE)):
        if w.inside(fx, ty) and w.fg[fx, ty] == T.DOOR.id:
            game.open_door(fx, ty)
        if w.inside(fx, ty) and w.fg[fx, ty] == T.GATE.id and game.can_open_gate(h, fx, ty):
            game.open_gate(fx, ty)
    if h.blocked and h.on_ground:
        # only jump over obstacles we can actually clear (1-2 tiles with headroom), never up a wall
        feet_row = int((h.feet - 1) // TILE)
        height = 0
        while height < 4 and w.inside(fx, feet_row - height) and T.SOLID[w.fg[fx, feet_row - height]]:
            height += 1
        headroom = all(not (w.inside(fx, feet_row - k) and T.SOLID[w.fg[fx, feet_row - k]])
                       for k in range(height, height + 3))
        if 0 < height <= 2 and headroom:
            it.jump = True
            it.jump_held = True
    if h.in_water > 0.3:
        it.jump_held = True
    return False


class Brain:
    kind = "base"

    def __init__(self, h):
        self.h = h

    def think(self, game, dt):
        pass


class FleeBrain(Brain):
    kind = "flee"

    def __init__(self, h, threat=None):
        super().__init__(h)
        self.threat = threat
        self.t = 8.0

    def think(self, game, dt):
        h = self.h
        it = h.intent
        it.clear()
        self.t -= dt
        thr = self.threat or h.last_attacker
        if thr is None or getattr(thr, "dead", False) or self.t <= 0:
            game.set_brain(h, getattr(h, "home_brain", "life"))
            return
        away = 1 if h.cx > thr.cx else -1
        walk_to(h, game, h.cx + away * 200, run=True)
        if random.random() < dt * 0.4:
            game.npc_say(h, "afraid")


class CombatBrain(Brain):
    kind = "combat"

    def __init__(self, h, target=None):
        super().__init__(h)
        self.target = target
        self.think_t = 0.0
        self.attack_cd = random.uniform(0.2, 0.8)
        self.block_hold = 0.0
        self.strafe = 0.0
        self.anchor = None   # leash position (guards)

    def pick_target(self, game):
        h = self.h
        best, bd = None, 420
        for t in game.targets_near(h.cx, 420):
            if t is h or getattr(t, "dead", False) or not game.hostile(h, t):
                continue
            d = abs(t.cx - h.cx) + abs(t.cy - h.cy) * 2
            if d < bd:
                best, bd = t, d
        return best

    def think(self, game, dt):
        h = self.h
        it = h.intent
        it.clear()
        self.think_t -= dt
        if self.target is None or getattr(self.target, "dead", False) or self.think_t <= 0:
            self.think_t = 0.6
            nt = self.pick_target(game)
            if nt is not None:
                self.target = nt
            elif self.target is None or getattr(self.target, "dead", False):
                game.set_brain(h, getattr(h, "home_brain", "life"))
                return
        t = self.target
        if t is None:
            return
        leash = getattr(h, "leash", None)
        if leash is not None and abs(t.cx - leash[0]) > leash[1]:
            # a wall guard does not leave his post to chase
            walk_to(h, game, leash[0], tol=10)
            h.facing = 1 if t.cx > h.cx else -1
            return
        if h.hp < h.max_hp * 0.22 and not getattr(h, "brave", False) and random.random() < dt:
            game.set_brain(h, "flee", threat=t)
            return
        self.fight(game, dt, t, free=True)

    def fight(self, game, dt, t, free=True, slot_x=None):
        h = self.h
        it = h.intent
        wd = h.weapon_def
        d = t.cx - h.cx
        dist = abs(d)
        face = 1 if d > 0 else -1
        h.weapon_drawn = True
        if wd.kind in ("bow", "crossbow"):
            want_lo, want_hi = 180, 480
            if free:
                if dist < want_lo:
                    walk_to(h, game, h.cx - face * 100, run=True)
                elif dist > want_hi:
                    walk_to(h, game, t.cx, run=False, tol=want_hi * 0.8)
            h.facing = face
            it.aim = game.aim_angle(h, t)
            if wd.kind == "bow":
                draw = h.action["draw"] if h.action and h.action["kind"] == "bow" else 0
                it.attack_held = draw < 0.85 or random.random() > dt * 3
            else:
                it.attack = random.random() < dt * 2
            return
        reach = wd.reach
        # enemy winding up? block (skill dependent)
        threat = False
        ta = getattr(t, "action", None)
        if ta and ta.get("kind") == "attack" and dist < ta["move"].reach + 20:
            mv = ta["move"]
            if ta["t"] < mv.windup and (t.facing * -d) > 0:
                threat = True
        # humans need time to react: skilled fighters see the blow coming sooner
        if threat and self.block_hold <= 0:
            if getattr(self, "react", None) is None:
                self.react = 0.24 - h.skill * 0.16 + random.uniform(0, 0.08)
            self.react -= dt
            if self.react <= 0:
                self.react = None
                if random.random() < h.skill * 0.8 + 0.05:
                    self.block_hold = 0.3 + random.uniform(0, 0.25)
        elif not threat:
            self.react = None
        if self.block_hold > 0:
            self.block_hold -= dt
            it.block = True
        hold_igel = h.formation_stance == "igel" and "brace" in wd.flags
        if hold_igel:
            it.block = True
            it.crouch = True
        if h.formation_stance == "schildwall" and h.shield is not None and dist > reach * 0.6:
            it.block = True
        # positioning
        if free:
            if dist > reach * 0.85:
                walk_to(h, game, t.cx - face * reach * 0.6, run=dist > 160)
            elif dist < reach * 0.35 and "polearm" in wd.flags:
                walk_to(h, game, h.cx - face * 30)
            else:
                it.mx = 0
        elif slot_x is not None:
            if abs(slot_x - h.cx) > 10:
                walk_to(h, game, slot_x, run=abs(slot_x - h.cx) > 40)
        if it.mx == 0 or not free:
            h.facing = face
        # attack (formations drop the guard for a quick thrust, then raise it again)
        self.attack_cd -= dt
        stance_hold = hold_igel or (h.formation_stance == "schildwall" and h.shield is not None)
        if stance_hold and self.block_hold <= 0 and dist < reach * 0.95 and self.attack_cd <= 0:
            it.block = False
        if dist < reach * 0.95 and abs(t.cy - h.cy) < 50 and self.attack_cd <= 0 and not it.block:
            if h.stamina > 20 or random.random() < 0.3:
                it.attack = True
                it.mx = 0
                self.attack_cd = random.uniform(0.35, 1.3) / (0.5 + h.skill)
                if random.random() < 0.15 and h.on_ground and free:
                    it.crouch = True   # low sweep / riposte
        if h.riposte_ready > 0 and dist < reach:
            it.crouch = True
            it.attack = True


class FormationBrain(CombatBrain):
    kind = "formation"

    def think(self, game, dt):
        h = self.h
        it = h.intent
        it.clear()
        hf = h.formation
        if hf is None or hf.dead:
            game.set_brain(h, "combat")
            return
        if hf.routed:
            game.set_brain(h, "flee", threat=hf.target.front[0] if hf.target and hf.target.front else None)
            return
        slot_x = hf.x - hf.facing * (getattr(h, "slot", 0) * 16 + 8)
        if h.mount is not None:
            # riders: ride with the block, strike anything in reach
            d = slot_x - h.cx
            it.mx = 0 if abs(d) < 8 else (1 if d > 0 else -1)
            it.run = abs(hf.speed) > 140 or abs(d) > 60
            enemy = self._enemy_in_reach(game, h.weapon_def.reach + 20)
            if enemy is not None:
                h.facing = 1 if enemy.cx > h.cx else -1
                if random.random() < dt * 3:
                    it.attack = True
            return
        enemy = self._enemy_in_reach(game, h.weapon_def.reach + 60)
        if enemy is not None:
            self.fight(game, dt, enemy, free=False, slot_x=slot_x)
        else:
            if abs(slot_x - h.cx) > 6:
                walk_to(h, game, slot_x, run=abs(slot_x - h.cx) > 30 or abs(hf.speed) > 90)
            else:
                h.facing = hf.facing
            if hf.stance == "schildwall" and h.shield is not None:
                it.block = True
            if hf.stance == "igel" and "brace" in h.weapon_def.flags:
                it.block = True
                it.crouch = True
            if hf.unit.ranged and hf.target is not None:
                h.facing = hf.facing

    def _enemy_in_reach(self, game, reach):
        h = self.h
        best, bd = None, reach
        for t in game.targets_near(h.cx, reach + 20):
            if t is h or getattr(t, "dead", False) or not game.hostile(h, t):
                continue
            d = abs(t.cx - h.cx)
            if d < bd and abs(t.cy - h.cy) < 60:
                best, bd = t, d
        return best


class FollowerBrain(CombatBrain):
    kind = "follow"

    def think(self, game, dt):
        h = self.h
        it = h.intent
        it.clear()
        leader = game.player
        if leader is None:
            return
        self.think_t -= dt
        if self.think_t <= 0:
            self.think_t = 0.5
            t = self.pick_target(game)
            self.target = t if t is not None and abs(t.cx - leader.cx) < 380 else None
        if self.target is not None and not getattr(self.target, "dead", False):
            self.fight(game, dt, self.target, free=True)
            return
        idx = getattr(h, "follow_idx", 0)
        spot = leader.cx - leader.facing * (40 + idx * 22)
        if abs(spot - h.cx) > 18:
            walk_to(h, game, spot, run=abs(spot - h.cx) > 90 or leader.state == "run")
        else:
            h.facing = leader.facing
        if leader.mount is not None and abs(leader.cx - h.cx) > 600:
            # can't keep up with a horse: they'll catch up at the next rest
            h.x = leader.cx - leader.facing * 120
            h.y = leader.y - 30


class LifeBrain(Brain):
    kind = "life"

    def __init__(self, h, person):
        super().__init__(h)
        self.p = person
        self.task = None
        self.task_t = 0.0
        self.say_cd = random.uniform(3, 12)
        self.work_t = 0.0
        self.wander_x = None
        self.greeted = 0.0
        self.alarm = 0.0

    def think(self, game, dt):
        h = self.h
        it = h.intent
        it.clear()
        p = self.p
        self.say_cd -= dt
        self.greeted = max(0.0, self.greeted - dt)
        hour = game.env.hour()
        # --- danger?
        self.alarm -= dt
        if self.alarm <= 0:
            self.alarm = 0.5
            threat = None
            for t in game.targets_near(h.cx, 260):
                if t is h or getattr(t, "dead", False):
                    continue
                if game.hostile(h, t) and (getattr(t, "kind", "") != "animal" or t.behaviour in ("predator",
                                                                                                    "aggressive")):
                    threat = t
                    break
            if threat is not None:
                if p.fighter:
                    game.set_brain(h, "combat", target=threat)
                    game.npc_say(h, "battle")
                else:
                    game.set_brain(h, "flee", threat=threat)
                    game.npc_say(h, "afraid")
                return
            fire = game.fire_near(h.cx, h.cy, 9)
            if fire is not None and not p.noble:
                self.task = ("fire", fire)
        # --- fire fighting
        if self.task and self.task[0] == "fire":
            fx, fy = self.task[1]
            if (fx, fy) not in game.world.fires:
                self.task = None
            else:
                if walk_to(h, game, fx * TILE + 8, run=True, tol=20):
                    h.action = {"kind": "work", "style": "stir", "speed": 4}
                    self.work_t += dt
                    if self.work_t > 1.2:
                        self.work_t = 0
                        game.extinguish(fx, fy)
                if self.say_cd <= 0:
                    self.say_cd = 6
                    game.npc_say(h, "fire")
                return
        # --- schedule
        rain = game.env.is_raining() or game.env.current()[0] == "sturm"
        if hour < 5.5 or hour >= 21.5:
            self.go_sleep(game, dt)
            return
        if h.state == "sleep" or getattr(h, "rest_state", None) == "sleep":
            h.rest_state = None
            h.state = "idle"
        if 7 <= hour < 12 or 13 <= hour < 18:
            if rain and p.job in ("farmer", "woodcutter", "fisher", "shepherd") and random.random() < 0.7:
                self.go_home(game)
            else:
                self.do_work(game, dt)
        elif 18 <= hour < 21.5:
            self.evening(game, dt)
        else:
            self.idle_near(game, p.home_x, dt)
        self.chatter(game, dt)

    # ---------------------------------------------------------------- schedule pieces
    def go_sleep(self, game, dt):
        h = self.h
        p = self.p
        if p.job == "guard":
            self.idle_near(game, p.work_x, dt, radius=40)
            h.carry_light = 0.9
            return
        if walk_to(self.h, game, p.bed_x * TILE + 8 if p.bed_x else p.home_x, tol=8):
            h.rest_state = "sleep"
            h.action = None

    def go_home(self, game):
        h = self.h
        h.action = None
        if walk_to(h, game, self.p.home_x, tol=20):
            h.intent.mx = 0

    def evening(self, game, dt):
        p = self.p
        spot = p.social_x or p.home_x
        self.idle_near(game, spot, dt, radius=60)

    def idle_near(self, game, x, dt, radius=50):
        h = self.h
        if self.wander_x is None or random.random() < dt * 0.15:
            self.wander_x = x + random.uniform(-radius, radius)
        h.action = None if h.action and h.action.get("kind") == "work" else h.action
        if walk_to(h, game, self.wander_x, tol=6):
            h.intent.mx = 0

    def do_work(self, game, dt):
        h = self.h
        p = self.p
        job = p.job
        w = game.world
        if job == "farmer":
            # walk along the field, harvest ripe wheat and sow again
            fx0, fx1 = p.field or (int(p.work_x // TILE) - 4, int(p.work_x // TILE) + 4)
            if self.task is None or self.task[0] != "field":
                self.task = ("field", random.randint(fx0, fx1))
            tx = self.task[1]
            if walk_to(h, game, tx * TILE + 8, tol=6):
                h.action = {"kind": "work", "style": "harvest", "speed": 2}
                self.work_t += dt
                if self.work_t > 2.0:
                    self.work_t = 0
                    g = w.ground_at(tx, max(0, p.g - 6))
                    y = g - 1
                    if w.inside(tx, y):
                        t = int(w.fg[tx, y])
                        fert = w.fert.get((tx, g), 1.0)
                        if t in T.RIPE:
                            crop = T.CROP_OF[t][0]
                            fert = max(0.15, fert - 0.25)
                            w.fert[(tx, g)] = fert
                            # Dreifelderwirtschaft: tired soil is left fallow (Brache) to recover
                            w.set(tx, y, T.CROPS[crop][0] if fert >= 0.45 else 0)
                            game.settlement_produce(p, {"oat": "oats"}.get(crop, crop), 2)
                            game.fx.debris(tx * TILE + 8, y * TILE + 8, (222, 190, 84), 4)
                        elif t == 0 and w.fg[tx, g] == T.FARMLAND.id and fert >= 0.7:
                            crop = getattr(p, "crop", None) or "wheat"
                            w.set(tx, y, T.CROPS[crop][0])
                    self.task = ("field", random.randint(fx0, fx1))
            return
        if job == "woodcutter":
            if self.task is None or self.task[0] != "tree":
                tree = game.find_tree(p.work_x // TILE, 60)
                self.task = ("tree", tree) if tree else ("idle", None)
            if self.task[0] == "tree":
                tx, ty = self.task[1]
                if w.fg[tx, ty] != T.LOG.id:
                    self.task = None
                    return
                if walk_to(h, game, tx * TILE - 14 if h.cx < tx * TILE else tx * TILE + 30, tol=8):
                    h.facing = 1 if tx * TILE + 8 > h.cx else -1
                    h.action = {"kind": "work", "style": "chop", "speed": 1.6}
                    self.work_t += dt
                    if self.work_t > 3.0:
                        self.work_t = 0
                        game.fell_tree(tx, ty, by=h)
                        game.settlement_produce(p, "wood", 4)
                        self.task = None
            else:
                self.idle_near(game, p.work_x, dt)
            return
        # stationary trades
        style = {"smith": "hammer", "priest": "pray", "monk": "pray", "fisher": "fish", "baker": "stir",
                 "innkeeper": "stir", "miner": "hammer", "weaver": "stir", "miller": "stir"}.get(job)
        if job in ("guard",):
            self.patrol(game, dt)
            return
        if job in ("child", "beggar", "shepherd") or style is None:
            self.idle_near(game, p.work_x, dt, radius=90 if job != "beggar" else 10)
            return
        if walk_to(h, game, p.work_x, tol=8):
            h.action = {"kind": "work", "style": style, "speed": 2.4 if style == "hammer" else 1.0}
            self.work_t += dt
            if style == "hammer" and int(h.anim_t * 2.4) != int((h.anim_t - dt) * 2.4):
                game.fx.sparks(h.cx + h.facing * 14, h.feet - 14, 5)
                game.sfx("anvil")
            if self.work_t > 20:
                self.work_t = 0
                game.settlement_produce(p, {"smith": "iron_ingot", "baker": "bread", "fisher": "fish",
                                            "miner": "iron_ore", "weaver": "cloth", "miller": "flour",
                                            "innkeeper": "beer"}.get(job, "wheat"), 1)

    def patrol(self, game, dt):
        h = self.h
        p = self.p
        a, b = p.patrol or (p.work_x - 200, p.work_x + 200)
        if self.task is None or self.task[0] != "patrol":
            self.task = ("patrol", b)
        if walk_to(h, game, self.task[1], tol=10):
            self.task = ("patrol", a if self.task[1] == b else b)
            self.idle_pause = 2.0

    def chatter(self, game, dt):
        h = self.h
        pl = game.player
        if pl is None or pl.dead:
            return
        d = abs(pl.cx - h.cx)
        if d < 90 and self.greeted <= 0 and abs(pl.cy - h.cy) < 60:
            self.greeted = 70.0
            if pl.rank >= 5 and self.p.rank < pl.rank:
                game.npc_say(h, "bow")
                h.rest_state = None
                h.kneel_t = 1.5
            else:
                game.npc_say(h, game.greeting_category())
            return
        if self.say_cd <= 0 and d < 300:
            self.say_cd = random.uniform(14, 30)
            env = game.env
            r = random.random()
            cat = self.p.job
            if r < 0.25:
                cat = {"regen": "rain", "sturm": "storm", "schnee": "snow", "nebel": "fog",
                       "klar": "sunny", "wolkig": "windy"}[env.current()[0]]
            elif r < 0.4:
                b = game.world.biome_at(int(h.cx // TILE))
                cat = "abyss" if b in ("edge",) else "lava" if b in ("volcanic", "lavasea", "ashland") else "rumor"
            elif r < 0.5 and game.society.at_war(self.p.kingdom):
                cat = "war"
            game.npc_say(h, cat)


class IdleBrain(Brain):
    """Story characters: stay near an anchor, face the player, say their piece."""
    kind = "idle"

    def __init__(self, h):
        super().__init__(h)
        self.say_t = random.uniform(4, 10)

    def think(self, game, dt):
        h = self.h
        it = h.intent
        it.clear()
        anchor = getattr(h, "anchor", h.cx)
        pl = game.player
        if abs(anchor - h.cx) > 30:
            walk_to(h, game, anchor, tol=10)
            return
        if pl is not None and abs(pl.cx - h.cx) < 200:
            h.facing = 1 if pl.cx > h.cx else -1
            self.say_t -= dt
            lines = getattr(h, "idle_lines", None)
            if lines and self.say_t <= 0:
                self.say_t = random.uniform(9, 16)
                line = random.choice(lines)
                h.say(line, t=5)
                game.hear(line, "story")


class ClimbBrain(Brain):
    """Up the Sturmleiter, over the parapet, then fight."""
    kind = "climb"

    def __init__(self, h):
        super().__init__(h)
        self.t = 0.0

    def think(self, game, dt):
        h = self.h
        it = h.intent
        it.clear()
        self.t += dt
        tgt = getattr(h, "climb_target", None)
        if tgt is None or self.t > 18:
            game.set_brain(h, "combat")
            return
        lx, top, wx = tgt
        feet_row = int((h.feet - 1) // TILE)
        side = 1 if wx > lx else -1
        if feet_row > top:
            if abs(h.cx - (lx * TILE + 8)) > 4 and not h.climbing:
                walk_to(h, game, lx * TILE + 8, tol=3)
            else:
                it.up = True
        else:
            it.mx = side
            it.up = True
            if h.on_ground and abs(h.cx - (lx * TILE + 8)) > 14:
                game.set_brain(h, "combat")


BRAINS = {"climb": ClimbBrain, "idle": IdleBrain, "life": LifeBrain, "combat": CombatBrain, "formation": FormationBrain, "follow": FollowerBrain,
          "flee": FleeBrain}
