"""A running game: world + simulation + entities + society + UI.

The Session owns everything and offers a small service API used by entities, brains, formations
and UI (targets_near, hostile, break_tile, fire_arrow, npc_say, ...). Systems never talk to each
other directly — they go through the session, which keeps the architecture modular.
"""
import math
import random

import pygame

from ..settings import TILE, SCREEN_W, SCREEN_H, SEA_LEVEL, DAY_LENGTH
from ..world.weather import Environment
from ..gfx.renderer import Camera
from ..poly.render import PolyRenderer as Renderer
from ..gfx.fx import FX
from ..gfx.rig import draw_humanoid
from ..combat.combat import CombatSystem
from ..combat.formation import Haufen
from ..entities.humanoid import Humanoid
from ..entities.player import Player
from ..entities.animals import Animal
from ..entities.boat import Boat
from ..entities.projectile import Projectile
from ..entities.npc import BRAINS
from ..items.items import ITEMS
from ..society.society import Society
from ..society.kingdoms import BY_KEY, KINGDOMS
from ..society import dialogue as D
from ..society.ranks import rank as rank_of
from .player_ctrl import PlayerController
from ..ui.hud import UI
from .. import audio
from .world_ops import WorldOps, ItemDrop, Construction  # noqa: F401
from ..poly import prefab as PF






class Session(WorldOps):
    def __init__(self, app, world, mode="sandbox", seed=1300, spawn=None, player_rank=1, quick_battle=None):
        self.app = app
        self.world = world
        self.mode = mode
        self.seed = seed
        self.rng = random.Random(seed)
        self.env = Environment(seed)
        self.camera = Camera()
        self.fx = FX()
        self.combat = CombatSystem(self)
        self.society = Society(world, seed)
        self.humanoids = []
        self.animals = []
        self.boats = []
        self.projectiles = []
        self.formations = []
        self.drops = []
        self.falling = []
        self.corpses = []
        self.constructions = []
        self.materialized = set()
        self.lod_t = 0.0
        self.spawn_t = 0.0
        self.door_timers = {}
        self.hitstop_t = 0.0
        self.void_queue = []
        self.messages = []
        self.day_seen = self.env.day
        self.story = None
        self.paused = False
        self.time_scale = 1.0
        self.fire_arrows = False
        self.crumble_t = 0.0
        self.tick = 0
        self.battle = None
        self.game_over = False
        self.zoom = 1.0
        self._view = None
        self.engines = []        # siege engines
        self.ladders = []        # raised assault ladders
        self.assaulters = []     # men who came over the wall
        # player
        self.player = Player(0, 0, self.rng, rank=player_rank)
        self.player.inv.money = 25
        self.place_player(spawn)
        self.add_humanoid(self.player, brain=None)
        self.ctrl = PlayerController(self)
        self.renderer = Renderer(world)
        self.ui = UI(self)
        self.camera.snap(self.player.cx, self.player.cy)
        self.audio = audio.Audio()

    # ================================================================== persistence
    def __getstate__(self):
        d = self.__dict__.copy()
        for k in ("app", "renderer", "ui", "audio", "_view", "ambient"):
            d[k] = None
        return d

    def restore(self, app):
        for k in ("engines", "ladders", "assaulters"):
            if not hasattr(self, k):
                setattr(self, k, [])
        if not hasattr(self.world, "gatehouses"):
            self.world.gatehouses = []
        self.app = app
        if not hasattr(self.world, "fert"):
            self.world.fert = {}
        if not hasattr(self.world, "smokers"):
            self.world.smokers = []
        self.renderer = Renderer(self.world)
        self.ui = UI(self)
        self.audio = audio.Audio()

    # ================================================================== setup
    def place_player(self, spawn):
        w = self.world
        if spawn is None:
            s = next((s for s in w.settlements if s["name"] == "Erlenbach"), w.settlements[0] if w.settlements
                     else None)
            x = (s["x0"] + 3) if s else w.w // 2
            g = s["g"] if s else w.ground_at(int(x), 0)
        else:
            x = spawn
            g = w.ground_at(int(x), max(0, int(w.surface[int(x)]) - 40))
        self.player.x = x * TILE
        self.player.y = g * TILE - self.player.h - 1
        self.player.fall_peak = self.player.y

    def give_start_kit(self, kind="sandbox"):
        inv = self.player.inv
        if kind == "story":
            for k, n in (("sichel", 1), ("bread", 3), ("seeds", 10), ("verband", 2)):
                inv.add(k, n)
            self.player.equip(weapon="fists")
            return
        for k, n in (("schwert", 1), ("axt", 1), ("hammer", 1), ("bogen", 1), ("arrow", 30), ("torch", 4),
                     ("bread", 5), ("seeds", 10), ("holzschild", 1), ("verband", 3), ("spitzhacke", 1),
                     ("schaufel", 1)):
            inv.add(k, n, force=True)
        inv.belt = ["schwert", "axt", "hammer", "bogen"]
        inv.selected = 0
        self.player.equip(weapon="schwert", shield="holzschild", armor="gambeson")
        self.sync_held()

    # ================================================================== entity management
    def add_humanoid(self, h, brain="life", **kw):
        self.humanoids.append(h)
        if brain:
            self.set_brain(h, brain, **kw)
        else:
            h.brain = None
        return h

    def set_brain(self, h, kind, **kw):
        if h is self.player:
            return
        cls = BRAINS[kind]
        if kind == "life":
            person = getattr(h, "person", None)
            if person is None:
                kind, cls = "combat", BRAINS["combat"]
                h.brain = cls(h)
                return
            h.brain = cls(h, person)
        elif kind == "flee":
            h.brain = cls(h, kw.get("threat"))
        elif kind == "combat":
            h.brain = cls(h, kw.get("target"))
        else:
            h.brain = cls(h)

    def remove_entity(self, e):
        e.removed = True

    def spawn_engine(self, key, x, side, facing, colors=None):
        from ..combat.siege import SiegeEngine
        e = SiegeEngine(self, key, x, side, facing, colors or ((120, 120, 120), (220, 220, 220)))
        self.engines.append(e)
        return e

    def spawn_horse(self, x, y, wild=True):
        a = Animal(x - 20, y - 31, "horse")
        if not wild:
            a.faction = "beast"
        self.animals.append(a)
        return a

    def mount(self, h, horse):
        if horse.rider is not None or horse.dead:
            return False
        h.mount = horse
        horse.rider = h
        h.blocking = False
        h.action = None
        if h.h != 42:
            h.y -= 42 - h.h
            h.h = 42
        if h is self.player:
            self.say_msg("[Aufsitzen|mount up]! Shift = [Galopp|gallop].")
        return True

    def dismount(self, h, thrown=False):
        horse = h.mount
        if horse is None:
            return
        horse.rider = None
        h.mount = None
        h.y = horse.y - 10
        h.x = horse.cx - h.w / 2 + (14 if thrown else 0)
        h.vy = -220 if thrown else -100
        h.fall_peak = h.y
        if thrown:
            h.stagger = 0.9
            h.hp -= 8

    def board_boat(self, h, boat):
        if boat.capsized:
            if boat.right():
                self.say_msg("You right the [Boot|boat].")
            return
        h.boat = boat
        boat.pilot = h
        h.deck_off = boat.w * 0.62 if boat.facing > 0 else boat.w * 0.38
        self.say_msg("[Leinen los|cast off]! W/S = [Segel|sail] up/down, Shift = [rudern|row], Space = leave.")

    def leave_boat(self, h, boat):
        h.boat = None
        if boat.pilot is h:
            boat.pilot = None
        if h in boat.passengers:
            boat.passengers.remove(h)
        h.y = boat.y - h.h - 6
        h.vy = -200
        h.fall_peak = h.y

    def targets_near(self, x, r):
        out = [h for h in self.humanoids if abs(h.cx - x) < r and not h.removed]
        out += [a for a in self.animals if abs(a.cx - x) < r and not a.removed]
        return out

    # ================================================================== factions
    def hostile_factions(self, fa, fb, a=None, b=None):
        if fa is None or fb is None:
            return False
        if fa == fb:
            return False
        if "wild" in (fa, fb):
            return True
        if "beast" in (fa, fb):
            return (a is not None and a is self.player) or (b is not None and b is self.player and False)
        if "bandit" in (fa, fb):
            return True
        if fa == "player":
            return self._player_hostile(fb, b)
        if fb == "player":
            return self._player_hostile(fa, a)
        return self.society.at_war(fa, fb)

    def _player_hostile(self, k, ent):
        if ent is not None and getattr(ent, "duel", False):
            return True
        if k in self.society.wanted:
            return True
        lg = self.player.liege
        if lg and (self.society.at_war(lg, k)):
            return True
        if self.battle and k in self.battle.enemy_sides:
            return True
        return False

    def hostile(self, a, b):
        if a is b:
            return False
        if getattr(a, "duel", False) and b is self.player or getattr(b, "duel", False) and a is self.player:
            return True
        return self.hostile_factions(getattr(a, "faction", None), getattr(b, "faction", None), a, b)

    # ================================================================== tiles






    def can_open_gate(self, h, x, y):
        s = self.world.settlement_at(x, margin=4)
        if s is None:
            return True
        si = self.world.settlements.index(s)
        owner = self.society.owner.get(si, s["kingdom"])
        return not self.hostile_factions(h.faction, owner, h, None)



    # ================================================================== fire




    def settlement_produce(self, person, key, n):
        m = self.society.markets.get(person.settlement)
        if m is not None:
            m.stock[key] = m.stock.get(key, 0) + n

    # ================================================================== items

    def pickup_text(self, key, n):
        d = ITEMS.get(key)
        if d:
            self.fx.text(self.player.cx, self.player.y - 20, f"+{n} {d.de}", (240, 220, 160), gloss=d.en, life=1.2)
            self.hear(f"[{d.de}|{d.en}]", "item", toast=False)

    def eat(self, p, key):
        d = ITEMS[key]
        if p.hunger >= 99 and p.hp >= p.max_hp:
            return
        p.inv.remove(key, 1)
        p.hunger = min(100.0, p.hunger + d.food)
        p.hp = min(p.max_hp, p.hp + d.food * 0.5)
        self.fx.text(p.cx, p.y - 16, f"{d.de}! [{'lecker'}]", (200, 240, 160), gloss=f"{d.en} — tasty")
        self.sfx("eat")
        self.sync_held()




    def bandage(self, h):
        from ..combat import injury as INJ
        inv = getattr(h, "inv", None)
        if not h.injury:
            self.ui.toast("You have no [Wunden|wounds] to bind.", 2)
            return False
        if inv is not None and not inv.remove("verband", 1):
            self.ui.toast("No [Verband|bandage]! (craft one from [Tuch|cloth])", 2)
            return False
        INJ.bandage(h)
        self.fx.text(h.cx, h.y - 16, "Verbunden", (230, 230, 210), gloss="bandaged")
        self.sync_held()
        return True

    def sync_held(self):
        p = self.player
        held = p.inv.held()
        d = ITEMS.get(held) if held else None
        if d is not None and d.weapon:
            p.equip(weapon=d.weapon)
        else:
            p.equip(weapon="fists")
        if p.weapon_def.kind == "bow":
            p.ammo = p.inv.count("arrow") + p.inv.count("fire_arrow")
        elif p.weapon_def.kind == "crossbow":
            p.ammo = p.inv.count("bolt")

    # ================================================================== projectiles
    def fire_arrow(self, h, aim, draw, kind="arrow"):
        f = h.facing
        if kind == "arrow":
            speed = 320 + 600 * draw
            dmg = h.weapon_def.dmg * (0.5 + draw * 0.7)
        else:
            speed = 950
            dmg = h.weapon_def.dmg
        if h is self.player:
            if kind == "arrow":
                use = "fire_arrow" if self.fire_arrows and h.inv.count("fire_arrow") else "arrow"
                if not h.inv.remove(use, 1):
                    if not h.inv.remove("fire_arrow", 1):
                        self.say_msg("Keine [Pfeile|arrows]!")
                        return
                    use = "fire_arrow"
                kind = use
            else:
                if not h.inv.remove("bolt", 1):
                    self.say_msg("Keine [Bolzen|bolts]!")
                    return
            self.sync_held()
        if self.env.is_raining() and kind != "bolt":
            speed *= 0.85
        vx = math.cos(aim) * speed * f
        vy = math.sin(aim) * speed
        p = Projectile(h.cx + f * 10, h.y + 14, vx, vy, h, kind, dmg)
        self.projectiles.append(p)
        self.sfx("bow" if kind != "bolt" else "crossbow")

    def fire_volley_arrow(self, hf, sx, sy, tx, ty, kind):
        dx = tx - sx
        dy = ty - sy
        if kind == "arrow":
            T_ = max(0.9, min(2.4, abs(dx) / 380.0))
            g = 520
        else:
            T_ = max(0.4, min(1.4, abs(dx) / 640.0))
            g = 300
        wind = self.env.wind * (70 if kind == "arrow" else 30)
        vx = dx / T_ - 0.5 * wind * T_ * 0.6
        vy = (dy - 0.5 * g * T_ * T_) / T_
        vx *= random.uniform(0.94, 1.06)
        vy *= random.uniform(0.95, 1.05)
        p = Projectile(sx, sy, vx, vy, None, kind, 16 if kind == "arrow" else 26)
        p.faction = hf.side
        self.projectiles.append(p)

    def aim_angle(self, h, t):
        v = 320 + 600 * 0.85 if h.weapon_def.kind == "bow" else 950
        g = 520 if h.weapon_def.kind == "bow" else 300
        x = abs(t.cx - h.cx)
        y = -((t.y + 16) - (h.y + 14))
        disc = v ** 4 - g * (g * x * x + 2 * y * v * v)
        if disc < 0 or x < 1:
            return -0.6
        theta = math.atan((v * v - math.sqrt(disc)) / (g * x))
        return -theta + random.uniform(-0.04, 0.04) * (1.5 - h.skill)

    # ================================================================== speech & learning
    def npc_ctx(self, h):
        p = getattr(h, "person", None)
        s = self.world.settlement_at(int(h.cx // TILE), margin=60)
        k = p.kingdom if p else h.faction
        kd = BY_KEY.get(k)
        enemies = self.society.enemies_of(k) if kd else []
        return {"player_rank": self.player.rank, "place": s["name"] if s else "hier",
                "lord": kd["ruler"] if kd else "unser Herr", "realm": kd["de"] if kd else "das Reich",
                "enemy": BY_KEY[enemies[0]]["de"] if enemies else "die Räuber", "price": self.rng.randint(2, 9)}

    def npc_say(self, h, cat):
        line = D.pick(cat, self.npc_ctx(h), self.rng)
        if not line:
            return
        from ..society import lingua
        line = lingua.get().weave(line)
        h.say(line, t=4.5)
        if abs(h.cx - self.player.cx) < 300 and abs(h.cy - self.player.cy) < 200:
            self.hear(line, cat)

    def hear(self, line, ctx="", toast=True):
        from ..society import lingua
        L = lingua.get()
        line = L.weave(line)
        new = self.player.dict.learn(line, ctx)
        if new and toast:
            self.ui.new_words(new)
        for de in L.count_text(line):
            e = L.words.get(de, {})
            self.ui.toast(f"Gemeistert: [{de}|{e.get('en', '')}] ✓ — no more translation for this word.", 4)
        self.player.stats["words"] = len(self.player.dict.words)

    def greeting_category(self):
        h = self.env.hour()
        if 5 <= h < 11:
            return "greet_morning"
        if 11 <= h < 18:
            return "greet_day"
        if 18 <= h < 22:
            return "greet_evening"
        return "greet_night"

    def say_msg(self, line, t=5.0):
        from ..society import lingua
        line = lingua.get().weave(line)
        self.messages.append([line, t])
        self.messages = self.messages[-6:]
        self.hear(line, "msg", toast=False)

    # ================================================================== events
    def emit(self, event, **kw):
        if self.story is not None:
            self.story.on_event(event, kw)
        if self.battle is not None:
            self.battle.on_event(event, kw)

    def on_death(self, h, killer):
        p = getattr(h, "person", None)
        if p is not None:
            p.alive = False
        if h is self.player:
            self.ui.death_screen()
            return
        if h.formation is None and h.faction != "player":
            if self.rng.random() < 0.5:
                self.drop_item("silver_coin", self.rng.randint(1, 8), h.cx, h.y + 10)
            if self.rng.random() < 0.12 and h.weapon_key not in ("fists",):
                self.drop_item(h.weapon_key, 1, h.cx, h.y + 10)
        if killer is self.player:
            self.player.stats["kills"] += 1
            if h.faction == "bandit":
                self.player.ehre += 2
                self.ui.toast("+2 [Ehre|honour] — a robber slain")
            elif getattr(h, "duel", False):
                self.player.ehre += 3
            elif not self.hostile(self.player, h):
                self.crime(h, "murder")
        self.emit("death", h=h, killer=killer)

    def on_animal_death(self, a, killer):
        for k, n in a.drops.items():
            self.drop_item(k, n, a.cx, a.y)
        if killer is self.player and a.species == "deer":
            k = self.world.kingdom_at(int(a.cx // TILE))
            if k in ("waldheim", "hochburg") and self.player.rank < 4:
                witnesses = [h for h in self.humanoids if not h.dead and h is not self.player and
                             abs(h.cx - a.cx) < 500 and getattr(h, "person", None)]
                if witnesses:
                    self.player.ehre -= 2
                    self.ui.toast("[Wilderei|poaching]! The duke's deer belong to the duke. −2 [Ehre|honour]")
        self.emit("animal_death", a=a, killer=killer)

    def crime(self, victim, what):
        k = getattr(victim, "faction", None)
        if k in BY_KEY:
            self.society.wanted.add(k)
            self.player.ehre -= 10
            self.ui.toast(f"[Verbrechen|crime]! You are [geächtet|outlawed] in {BY_KEY[k]['de']}.")
            for h in self.humanoids:
                if getattr(h, "person", None) and h.person.fighter and h.faction == k and abs(h.cx - victim.cx) < 900:
                    self.set_brain(h, "combat", target=self.player)
                    self.npc_say(h, "crime")

    def on_rout(self, hf):
        if hf.side == "player":
            self.ui.toast(f"Your {hf.unit.de} [fliehen|flee]!")
        else:
            self.ui.toast(f"The enemy {hf.unit.de} [fliehen|flee]!")
        self.emit("rout", hf=hf)

    def add_corpse_sprite(self, hf, x, y):
        """A soldier falls out of a formation's ranks: he becomes a real ragdoll body."""
        from ..entities.ragdoll import Ragdoll
        from ..gfx.rig import world_joints
        proto = hf.protos[self.rng.randrange(len(hf.protos))]
        h = Humanoid(x - 7, y - 43, dict(proto.look), hf.side, hf.unit.de)
        h.equip(weapon=proto.weapon_key, shield=hf.unit.shield or "", armor=hf.unit.armor,
                helmet=hf.unit.helmet or "")
        h.facing = hf.facing
        h.dead = True
        h.state = "dead"
        h.hp = 0
        h.brain = None
        h.weapon_drawn = True
        h.ragdoll = Ragdoll(world_joints(h), (-hf.facing * self.rng.uniform(50, 170), -self.rng.uniform(60, 220)),
                            self.rng.uniform(-80, 80))
        self.humanoids.insert(0, h)
        self.corpse_bodies = getattr(self, "corpse_bodies", [])
        self.corpse_bodies.append(h)
        if len(self.corpse_bodies) > 60:
            self.corpse_bodies.pop(0).removed = True
        self.fx.blood(x, y - 20, 5, -hf.facing)

    def hitstop(self, t):
        self.hitstop_t = max(self.hitstop_t, t)

    def sfx(self, name):
        if self.audio:
            self.audio.play(name)

    # ================================================================== LOD: people & animals

    def materialize(self, si):
        s = self.world.settlements[si]
        env_h = self.env.hour()
        night = env_h < 5.5 or env_h >= 21.5
        for pid in self.society.by_settlement.get(si, []):
            p = self.society.people[pid]
            if not p.alive:
                continue
            x = (p.bed_x * TILE + 8 if night and p.bed_x else p.home_x) if night else p.work_x
            x += self.rng.uniform(-20, 20)
            x = self.free_spot(x, p.g * TILE)
            gy = self.world.ground_y(x, p.g * TILE - 30, 60)
            h = Humanoid(x - 7, gy - 43, p.look, p.kingdom, p.name, p.rank)
            h.person = p
            h.hp = p.hp
            wk, sk, ak, hk = p.gear
            h.equip(weapon=wk, shield=sk or "", armor=ak, helmet=hk or "")
            h.weapon_drawn = False
            h.skill = 0.6 if p.fighter else 0.25
            h.brave = p.fighter
            h.home_brain = "life"
            h.unaware = True
            h.settlement = si
            if p.noble:
                h.max_hp = h.hp = max(h.hp, 140)
            self.add_humanoid(h, "life")
        # livestock
        if s["type"] in ("village", "hamlet", "monastery"):
            fields = [b for b in s["buildings"] if b["kind"] == "field"] or s["buildings"][:1]
            for i in range(self.rng.randint(4, 8)):
                b = self.rng.choice(fields)
                sp = self.rng.choice(["cow", "sheep", "sheep", "pig", "chicken", "chicken"])
                x = (b["x0"] + self.rng.random() * (b["x1"] - b["x0"] + 1)) * TILE
                g = self.world.ground_at(int(x // TILE), max(0, s["g"] - 3))
                a = Animal(x, g * TILE - 30, sp, faction="beast")
                a.y = g * TILE - a.h - 1
                a.settlement = si
                a.home_x = x
                self.animals.append(a)
        if s["type"] in ("castle", "capital"):
            hall = next((b for b in s["buildings"] if b["kind"] == "hall"), None)
            hx = (hall["x0"] - 3) if hall else s["x0"] + 20
            for i in range(2):
                tx = self.free_column(hx - i * 3, s["g"], direction=-1)
                x = tx * TILE + 8
                a = self.spawn_horse(x, s["g"] * TILE, wild=False)
                a.settlement = si
                a.tethered = True
                a.for_sale = True
        if s["type"] == "port":
            dock = next((b for b in s["buildings"] if b["kind"] == "dock"), None)
            if dock and not any(getattr(b, "settlement", None) == si for b in self.boats):
                bx = dock["berth"] * TILE
                kd = BY_KEY[s["kingdom"]]
                boat = Boat(bx - 56, SEA_LEVEL * TILE - 12, colors=kd["colors"])
                boat.settlement = si
                boat.for_sale = True
                boat.facing = 1 if dock["x1"] > s["x0"] + (s["x1"] - s["x0"]) / 2 else -1
                self.boats.append(boat)
        self.materialized.add(si)

    def dematerialize(self, si):
        for h in self.humanoids:
            if getattr(h, "settlement", None) == si and h is not self.player and h not in self.player.followers:
                if getattr(h, "person", None):
                    h.person.hp = max(30.0, h.hp) if not h.dead else 0
                h.removed = True
        for a in self.animals:
            if getattr(a, "settlement", None) == si and a.rider is None and a.owner is not self.player:
                a.removed = True
        for b in self.boats:
            if getattr(b, "settlement", None) == si and b.pilot is None and b.owner is not self.player:
                b.removed = True
        self.materialized.discard(si)

    def update_lod(self, dt):
        self.lod_t -= dt
        if self.lod_t > 0:
            return
        self.lod_t = 1.0
        ptx = self.player.cx / TILE
        for si, s in enumerate(self.world.settlements):
            d = max(s["x0"] - ptx, ptx - s["x1"], 0)
            if d < 130 and si not in self.materialized:
                self.materialize(si)
            elif d > 200 and si in self.materialized:
                self.dematerialize(si)
        # wildlife
        self.spawn_t -= 1.0
        if self.spawn_t <= 0:
            self.spawn_t = 3.0
            self.spawn_wildlife()
        for a in self.animals:
            if getattr(a, "settlement", None) is None and a.rider is None and a.owner is None and \
                    abs(a.cx - self.player.cx) > 2200:
                a.removed = True
        for h in self.humanoids:
            if h is not self.player and getattr(h, "settlement", None) is None and h.formation is None and \
                    h not in self.player.followers and abs(h.cx - self.player.cx) > 3000 and not \
                    getattr(h, "keep", False):
                h.removed = True
        for ar in self.society.armies:
            pass

    def spawn_wildlife(self):
        if self.mode == "battle":
            return
        w = self.world
        p = self.player
        wild = [a for a in self.animals if getattr(a, "settlement", None) is None and a.owner is None]
        if len(wild) >= 10:
            return
        side = self.rng.choice((-1, 1))
        x = p.cx + side * self.rng.uniform(800, 1200)
        tx = int(x // TILE)
        if not (w.abyss_w < tx < w.w - 60):
            return
        if w.settlement_at(tx, margin=40):
            return
        b = w.biome_at(tx)
        if b in ("ocean", "lavasea") or w.surface[tx] >= SEA_LEVEL:
            # fish in the sea
            if b == "ocean":
                for _ in range(3):
                    fy = (SEA_LEVEL + self.rng.randint(4, 30)) * TILE
                    if w.water_level(x) is not None and fy < w.surface_y(x) - 8:
                        self.animals.append(Animal(x, fy, "fish"))
            return
        night = self.env.is_night()
        table = {
            "plains": ["deer", "horse", "horse", "boar"], "edge": ["horse", "deer"],
            "forest": ["deer", "deer", "boar"] + (["wolf", "wolf"] if night else []),
            "moor": ["boar", "deer"], "hills": ["deer", "boar", "sheep"],
            "mountains": ["deer", "bear"] + (["wolf"] if night else []),
            "vineyard": ["deer"], "coast": ["deer"], "snow": ["wolf", "deer", "bear"],
            "ashland": ["boar"], "volcanic": [], "islet": [],
        }.get(b, [])
        if not table:
            return
        sp = self.rng.choice(table)
        g = w.ground_at(tx, max(0, int(w.surface[tx]) - 30))
        n = 3 if sp == "wolf" else 1 if sp in ("bear", "boar") else self.rng.randint(1, 3)
        for i in range(n):
            a = Animal(x + i * 30, g * TILE - 40, sp)
            a.y = g * TILE - a.h - 1
            self.animals.append(a)

    # ================================================================== armies
    def materialize_army(self, ar):
        kd = BY_KEY[ar.kingdom]
        tgt = self.world.settlements[ar.target]
        tx = (tgt["x0"] + tgt["x1"]) / 2 * TILE
        facing = 1 if tx > ar.x else -1
        x = ar.x
        ar.haufen = []
        order = sorted(ar.units, key=lambda u: (u[0] in ("bogen", "armbrust"), u[0] in ("ritter", "reisige")))
        for ukey, cnt in order:
            if cnt <= 0:
                continue
            hf = Haufen(self, ar.kingdom, ukey, cnt, x, facing, kd["colors"])
            hf.order = "vorwaerts"
            hf.army = ar
            self.formations.append(hf)
            ar.haufen.append(hf)
            x -= facing * (hf.width() + 40)
        ar.materialized = True
        # the defenders muster if their town is close
        owner = self.society.owner.get(ar.target)
        if owner and abs(tx - ar.x) < 260 * TILE:
            dk = BY_KEY[owner]
            gx = (tgt["x0"] if facing > 0 else tgt["x1"]) * TILE - facing * 120
            for ukey, cnt in (("speer", 20), ("bogen", 12)):
                hf = Haufen(self, owner, ukey, cnt, gx, -facing, dk["colors"])
                hf.order = "halt"
                self.formations.append(hf)
                gx += facing * (hf.width() + 30)
        self.ui.toast(f"An [Heer|army] of {kd['de']} approaches! ([Achtung|beware])")

    def dematerialize_army(self, ar):
        ar.units = [[h.unit.key, h.count] for h in ar.haufen if not h.dead]
        for hf in ar.haufen:
            hf.dead = True
            for f in hf.front:
                f.removed = True
        ar.haufen = []
        ar.materialized = False

    def ai_command(self, hf, dt):
        """Simple field commander for non-player formations."""
        if hf.side == "player" or hf.routed:
            return
        hf.ai_t = getattr(hf, "ai_t", 0.0) - dt
        if hf.ai_t > 0:
            return
        hf.ai_t = 1.0
        if getattr(hf, "no_advance", False):
            if hf.order not in ("halt",):
                hf.order = "halt"
            return
        ldr = hf.leader
        if hf.order == "folgt" and ldr is not None and getattr(ldr, "kind", "") == "engine" and not ldr.dead:
            return
        enemy, dist = hf.nearest_enemy()
        player_threat = abs(self.player.cx - hf.x) < 500 and self.hostile_factions(hf.side, "player")
        if enemy is None and not player_threat:
            if getattr(hf, "army", None) is None and hf.order != "halt":
                hf.order = "halt"
            return
        if enemy is None:
            if hf.unit.ranged:
                hf.order = "halt"
            elif hf.order == "halt":
                hf.order = "vorwaerts"
            return
        u = hf.unit
        if hf.blocked_by_tile is not None and not u.ranged:
            hf.order = "angriff"     # storm the gate / wall in the way
            return
        if u.ranged:
            hf.order = "halt" if dist < 700 else "vorwaerts"
            if dist < 160 and enemy.unit.cavalry:
                hf.order = "zurueck"
            return
        if u.cavalry:
            if hf.order != "zurueck":
                hf.order = "angriff" if dist < 650 else "vorwaerts"
            return
        if enemy.unit.cavalry and "brace" in hf.protos[0].weapon_def.flags and dist < 500:
            hf.set_order("igel", shout=hf.stance != "igel")
            hf.order = "halt"
            return
        incoming = any(p.faction != hf.side and abs(p.x - hf.x) < 400 for p in self.projectiles[-40:])
        if incoming and hf.unit.shield and hf.stance != "schildwall" and dist > 200:
            hf.set_order("schildwall")
        elif dist < 180 and hf.stance == "schildwall" and hf.unit.quality < 0.7:
            hf.set_order("normal", shout=False)
        if hf.stance == "igel" and not enemy.unit.cavalry:
            hf.set_order("normal", shout=False)
        hf.order = "angriff" if dist < 140 else "vorwaerts"

    # ================================================================== the void
    def handle_void(self, e, dt):
        if e.void_fall <= 0:
            return False
        if e is self.player:
            if e.void_fall > 2.6:
                self.sky_drop(e)
            return False
        if e.void_fall > 1.0:
            e.removed = True
            if isinstance(e, Humanoid) and not e.dead and self.rng.random() < 0.6:
                self.void_queue.append([self.rng.uniform(2, 6), e])
            return True
        return False

    def sky_drop(self, e, near=None):
        w = self.world
        if near is None:
            for _ in range(40):
                tx = self.rng.randint(w.abyss_w + 300, w.w - 600)
                if w.biome_at(tx) not in ("lavasea", "volcanic"):
                    break
        else:
            tx = int(near // TILE) + self.rng.randint(-30, 30)
        e.x = tx * TILE
        e.y = -300
        e.vy = 0
        e.vx = 0
        e.void_fall = 0
        e.fall_peak = e.y
        e.skyfall = True
        e.removed = False
        if e.mount is not None:
            self.dismount(e)
        if e is self.player:
            self.ui.toast("Der [Himmel|sky] spuckt dich aus! — the sky spits you out!")
            self.say_msg("You fell through the [Abgrund|abyss]… and out of the [Himmel|sky] far away.")
            self.camera.snap(e.cx, e.cy)
            self.emit("skyfall", x=tx)

    # ================================================================== update
    def update(self, dt, events, keys, mouse_buttons, mouse_pos):
        if self.ui.modal_blocks():
            self.ui.update(dt, events)
            self.renderer.invalidate()
            return
        self.ui.update(dt, events)
        if self.hitstop_t > 0:
            self.hitstop_t -= dt
            dt = dt * 0.15
        dt *= self.time_scale
        self.tick += 1
        p = self.player
        # input
        if not self.ui.captures_input():
            self.ctrl.handle(dt, keys, mouse_buttons, mouse_pos, events)
        else:
            p.intent.clear()
        # environment
        biome = self.world.biome_at(int(p.cx // TILE))
        ev = self.env.update(dt, biome)
        if ev == "lightning":
            self.lightning_strike()
        if self.env.day != self.day_seen:
            self.day_seen = self.env.day
            self.new_day()
        # brains & entities
        for h in self.humanoids:
            if h.removed:
                continue
            if h is not p and getattr(h, "brain", None) is not None and not h.dead:
                if abs(h.cx - p.cx) < 2600:
                    h.brain.think(self, dt)
                else:
                    h.intent.clear()
            kt = getattr(h, "kneel_t", 0)
            if kt > 0:
                h.kneel_t = kt - dt
                h.rest_state = "kneel" if h.kneel_t > 0 else None
            if abs(h.cx - p.cx) < 2600 or h is p:
                if getattr(h, "boat", None) is None:
                    h.update(self, dt)
                else:
                    h.anim_t += dt
                    h.state = "idle"
                    from ..gfx.rig import compute_pose
                    h.pose = compute_pose(h)
            self.handle_void(h, dt)
            if getattr(h, "skyfall", False) and h.on_ground and h.vy == 0:
                h.skyfall = False
                if h.in_water < 0.2:
                    h.hp -= 25
                    self.fx.dust(h.cx, h.feet, 20)
                    self.camera.shake = 8 if h is p else self.camera.shake
                    if h.hp <= 0:
                        h.die(self, None)
                h.fall_peak = h.y
        for a in self.animals:
            if not a.removed and abs(a.cx - p.cx) < 2600:
                a.update(self, dt)
                self.handle_void(a, dt)
                if a.species in ("cow", "sheep", "pig", "horse") and self.rng.random() < dt * 0.006 and not a.dead:
                    self.drop_item("mist", 1, a.cx, a.feet - 6)
        self.trample(dt)
        for b in self.boats:
            if abs(b.cx - p.cx) < 3000:
                b.update(self, dt)
        for pr in self.projectiles:
            pr.update(self, dt)
        for hf in self.formations:
            if not hf.dead:
                self.ai_command(hf, dt)
                hf.update(dt)
        for e in self.engines:
            e.update(self, dt)
        from ..combat import siege as SIEGE
        SIEGE.update(self, dt)
        self.combat.update(dt)
        for d in self.drops:
            d.update(self, dt)
        for fb in self.falling:
            fb.update(self, dt)
        self.update_constructions(dt)
        # void re-entry
        for item in list(self.void_queue):
            item[0] -= dt
            if item[0] <= 0:
                self.void_queue.remove(item)
                e = item[1]
                self.sky_drop(e, near=p.cx)
                e.removed = False
                self.humanoids.append(e)
                self.fx.text(e.cx, 100, "Es regnet Ritter!", (255, 220, 160), gloss="it's raining knights!")
        # world simulation
        ptx = int(p.cx // TILE)
        self.world_tick(dt)
        for e in self.humanoids:
            if e.blocked_by is not None and not e.dead:
                self.door_contact(e)
        self.update_doors(dt)
        self.update_lod(dt)
        self.society.update_armies(dt, self)
        self.update_edges(dt)
        self.update_player_needs(dt)
        if self.story is not None:
            self.story.update(dt)
        if self.battle is not None:
            self.battle.update(dt)
        self.fx.update(dt)
        if getattr(self, "ambient", None) is None:
            from ..gfx.ambient import Ambient
            self.ambient = Ambient()
        self.ambient.update(self, dt, self.view_size())
        for c in self.corpses:
            c[4] += dt
        # cleanup
        self.humanoids = [h for h in self.humanoids if not h.removed and not (h.dead and h.dead_t > 40 and h is not p)]
        self.animals = [a for a in self.animals if not a.removed and not (a.dead and a.dead_t > 30)]
        self.projectiles = [x for x in self.projectiles if not x.removed]
        self.formations = [f for f in self.formations if not f.dead]
        self.drops = [d for d in self.drops if not d.removed]
        self.falling = [f for f in self.falling if not f.removed]
        self.boats = [b for b in self.boats if not b.removed]
        self.engines = [e for e in self.engines if not e.removed]
        self.player.followers = [f for f in self.player.followers if not f.dead and not f.removed]
        self.player.haufen = [h for h in self.player.haufen if not h.dead]
        for m in self.messages:
            m[1] -= dt
        self.messages = [m for m in self.messages if m[1] > 0]
        # camera
        lead = p.vx * 0.35 if p.mount is None else p.mount.vx * 0.6
        if p.boat is not None:
            lead = p.boat.vx * 0.8
        self.camera.follow(p.cx, p.cy, dt, self.world, lead=lead, view=self.view_size())

    def view_size(self):
        z = getattr(self, "zoom", 1.0)
        return (int(SCREEN_W / z), int(SCREEN_H / z))

    def set_zoom(self, z):
        p = self.player
        old = self.view_size()
        self.zoom = z
        new = self.view_size()
        self.camera.x += (old[0] - new[0]) / 2
        self.camera.y += (old[1] - new[1]) * 0.58

    def update_player_needs(self, dt):
        p = self.player
        if p.dead:
            return
        p.hunger = max(0.0, p.hunger - dt * 0.05)
        if p.hunger <= 0:
            p.hp -= dt * 0.5
            if p.hp <= 0:
                p.die(self, None)
        elif p.hunger > 50 and p.hp < p.max_hp:
            p.hp = min(p.max_hp, p.hp + dt * 0.6)

    def new_day(self):
        self.society.daily(self.env.day, self.world)
        w = self.world
        self.grow_crops(1.0)
        p = self.player
        if p.fiefs:
            income = 0
            for si in p.fiefs:
                s = self.world.settlements[si]
                income += {"village": 25, "hamlet": 10, "town": 60, "castle": 30, "city": 120}.get(s["type"], 20)
            p.inv.money += income
            self.ui.toast(f"[Abgaben|dues] from your [Lehen|fiefs]: +{income} Pf")
        if p.citizen_of is None and p.rank == 0:
            s = self.world.settlement_at(int(p.cx // TILE), margin=10)
            if s and s["type"] in ("city", "town", "capital") and s["kingdom"] == "luebenau":
                p.days_in_city += 1
        for text, gl in self.society.news[-3:]:
            self.say_msg(text, 8)
        self.society.news.clear()
        self.emit("day", day=self.env.day)




    # ================================================================== construction


    # ================================================================== your troops
    UNIT_FOR_WEAPON = {"speer": "speer", "spiess": "spiess", "hellebarde": "hellebarde", "bogen": "bogen",
                       "armbrust": "armbrust", "lanze": "ritter"}

    def form_up(self):
        """'Formiert euch!' — your loose followers merge into a single Haufen."""
        p = self.player
        fol = [f for f in p.followers if not f.dead]
        if len(fol) < 3:
            self.ui.toast("You need at least 3 followers to form a [Haufen|formation].")
            return
        votes = {}
        for f in fol:
            u = self.UNIT_FOR_WEAPON.get(f.weapon_key)
            if u is None:
                u = "schild" if f.shield is not None and f.armor.key != "kleidung" else "bauern"
            votes[u] = votes.get(u, 0) + 1
        unit = max(votes, key=votes.get)
        colors = BY_KEY[p.liege]["colors"] if p.liege in BY_KEY else ((110, 120, 80), (230, 220, 190))
        hf = Haufen(self, "player", unit, len(fol), p.cx + p.facing * 40, p.facing, colors, leader=p)
        for i, f in enumerate(fol):
            if i < len(hf.members):
                hf.members[i]["hp"] = f.hp
            f.removed = True
        p.followers = []
        hf.order = "folgt"
        self.formations.append(hf)
        p.haufen.append(hf)
        hf.selected = True
        p.say(D.ORDERS["formiert"][0], t=2.5)
        self.hear(D.ORDERS["formiert"][0], "orders")
        self.ui.toast(f"{len(fol)} men form a [Haufen|formation] of {hf.unit.de}!")
        self.emit("formed", hf=hf)

    def disband(self):
        p = self.player
        if not p.haufen:
            return
        hf = p.haufen[p.selected_haufen] if p.selected_haufen >= 0 else p.haufen[-1]
        n = 0
        while hf.members and n < 12:
            m = hf.members.pop()
            proto = hf.protos[m["proto"]]
            x = hf.x - hf.facing * (20 + n * 14)
            g = self.world.ground_at(int(x // TILE), max(0, int(self.world.surface[int(x // TILE)]) - 30))
            h = Humanoid(x - 7, g * TILE - 43, dict(proto.look), "player", hf.unit.de)
            h.equip(weapon=proto.weapon_key, shield=hf.unit.shield or "", armor=hf.unit.armor,
                    helmet=hf.unit.helmet or "")
            h.hp = m["hp"]
            h.follow_idx = len(p.followers)
            h.keep = True
            h.brave = True
            self.add_humanoid(h, "follow")
            p.followers.append(h)
            n += 1
        for f in list(hf.front):
            f.formation = None
            f.faction = "player"
            f.follow_idx = len(p.followers)
            f.keep = True
            self.set_brain(f, "follow")
            p.followers.append(f)
        hf.front = []
        if not hf.members:
            hf.dead = True
        p.say(D.ORDERS["aufloesen"][0], t=2.5)

    # ================================================================== interaction
    def interact(self):
        p = self.player
        w = self.world
        if p.dead:
            return
        if p.boat is not None:
            self.leave_boat(p, p.boat)
            return
        if p.mount is not None:
            self.dismount(p)
            return
        # people
        best, bd = None, 46
        for h in self.humanoids:
            if h is p or h.dead or h.formation is not None:
                continue
            d = abs(h.cx - p.cx)
            if d < bd and abs(h.cy - p.cy) < 40:
                best, bd = h, d
        if best is not None:
            self.ui.open_dialogue(best)
            return
        # horses
        for a in self.animals:
            if a.species == "horse" and not a.dead and abs(a.cx - p.cx) < 34 and abs(a.cy - p.cy) < 40:
                if getattr(a, "for_sale", False) and a.owner is not p:
                    self.ui.toast("This [Pferd|horse] belongs to the stable. Buy it from the stable master.")
                    return
                if a.owner is None:
                    a.owner = p
                    self.ui.toast("You caught a wild [Pferd|horse]! It is yours now.")
                self.mount(p, a)
                self.emit("mount")
                return
        # boats
        for b in self.boats:
            if abs(b.cx - p.cx) < b.w / 2 + 10 and abs(b.y - p.feet) < 60:
                if getattr(b, "for_sale", False) and b.owner is not p:
                    self.ui.toast("This [Boot|boat] is for sale at the harbour [Kontor|trading house].")
                    return
                self.board_boat(p, b)
                self.emit("board")
                return
        # siege engines you own
        for e in self.engines:
            if not e.dead and e.side == "player" and abs(e.x - p.cx) < e.w / 2 + 30:
                e.toggle(self)
                return
        # at a workbench: work there (whatever you carry goes onto the bench)
        for d in w.near("decor_chunks", p.cx - 60, p.cx + 60):
            if d.kind == "workbench" and not d.gone and abs(d.x - p.cx) < 34 and abs(d.y - p.feet) < 30:
                self.ui.open_lab(d)
                return
        # what you carry: set it down in front of you
        if getattr(p, "carrying", None) is not None:
            self.put_down(p)
            return
        # loose things: pick them up (into the bag, or into your arms)
        mx, my = self.ctrl.mouse_world
        near_mouse = math.hypot(mx - p.cx, my - p.cy) < 90
        best, bd = None, 44
        for o in w.objects:
            if o.removed or o.anchored and o.shape_key != "door" or o.crown is not None:
                continue
            for qx, qy in ((p.cx, p.cy + 8),) + (((mx, my),) if near_mouse else ()):
                d = math.hypot(o.x - qx, o.y - qy) - o.radius * 0.6
                if d < bd:
                    best, bd = o, d
        if best is not None:
            if best.anchored and best.shape_key == "door":
                self.toggle_object_door(best)
            else:
                self.pick_up(p, best)
            return
        # doors
        pc = self.door_near(p.cx + p.facing * 10, p.feet - 20, 34)
        if pc is not None:
            if pc.open:
                PF.toggle_door(w, pc, False)
                self.door_timers.pop(pc.id, None)
            else:
                b_ = PF.building(w, pc.bld)
                if b_ is not None and b_.kind in ("wall", "gatehouse") and not self.can_open_gate(p, int(pc.cx // TILE), 0):
                    self.ui.toast("The [Tor|gate] is barred against you.")
                else:
                    self.open_door_piece(pc, t=6.0)
            return
        # fittings and furniture
        best, bd = None, 34
        for d in w.near("decor_chunks", p.cx - 80, p.cx + 80):
            if d.gone or d.kind in ("bush", "flowers", "fern", "reeds", "seaweed", "shell", "heather", "vine",
                                    "torchpost", "chain", "gablehead", "sails", "flag", "banner", "cross", "bell"):
                continue
            dx = abs(d.x - p.cx) - (d.w / 2 if d.kind == "plot" else 0)
            if dx < bd and d.y - d.h - 30 < p.feet < d.y + 20:
                best, bd = d, dx
        if best is not None and self.use_decor(best):
            return

    def use_decor(self, d):
        p = self.player
        w = self.world
        k = d.kind
        if k == "sign":
            self.ui.toast("[Wegweiser|signpost]: " + d.data.get("text", "…").replace("\n", "   "), 7)
        elif k == "chest":
            c = d.data.setdefault("items", {})
            got = [(kk, n) for kk, n in c.items() if n]
            if d.data.get("fresh", True) and not got and not d.data.get("sunken"):
                d.data["fresh"] = False
                c.update(self.rng.choice([{"bread": 2}, {"silver_coin": self.rng.randint(3, 15)}, {"cloth": 1},
                                          {"verband": 1}, {}]))
                got = [(kk, n) for kk, n in c.items() if n]
            if not got:
                self.ui.toast("The [Truhe|chest] is [leer|empty].")
            else:
                s = w.settlement_at(int(d.x // TILE), margin=2)
                for kk, n in got:
                    p.inv.add(kk, n)
                    self.pickup_text(kk, n)
                d.data["items"] = {}
                if s is not None and self.rng.random() < 0.5:
                    witnesses = [h for h in self.humanoids if getattr(h, "person", None) and not h.dead and
                                 abs(h.cx - p.cx) < 200 and h is not p]
                    if witnesses:
                        self.npc_say(witnesses[0], "thief")
                        p.ehre -= 3
                        self.ui.toast("[Dieb|thief]! −3 [Ehre|honour]")
        elif k == "bed":
            self.sleep()
        elif k == "plot":
            if not self.harvest(p.cx, by=p):
                pl, st = self.plot_at(p.cx)
                if st is not None and st[0] is not None:
                    self.ui.toast(f"The {st[0]} is not ripe yet ({int(st[1] * 100)}%).", 2)
                else:
                    return False
        elif k == "altar":
            if getattr(p, "prayed_day", -1) != self.env.day:
                p.prayed_day = self.env.day
                p.ehre += 1
                self.ui.toast("You pray. [Amen|amen]. +1 [Ehre|honour]")
            else:
                self.ui.toast("[Gott|God] has heard you today already.")
        elif k in ("well", "bucket"):
            p.hunger = min(100, p.hunger + 3)
            self.ui.toast("Fresh [Wasser|water] from the [Brunnen|well].")
        elif k == "workbench":
            self.ui.open_lab(d)
        elif k in ("anvil", "forge", "oven", "loom", "table", "hearth", "barrel"):
            self.ui.open("inventory")
        elif k == "throne":
            self.ui.toast("The [Thron|throne]. Sitting on it uninvited would be… unwise.")
        elif k == "winch":
            from ..combat import siege as SIEGE
            gh = SIEGE.gatehouse_near(self, d.x)
            if gh is None:
                return False
            owner = SIEGE.gatehouse_owner(self, gh)
            if owner is not None and self.hostile_factions("player", owner, p, None):
                self.ui.toast("Not your castle! The guards would cut you down at the [Winde|winch].")
                return True
            gh.auto = False
            SIEGE.set_defenses(self, gh, not gh.closed)
            self.ui.toast("[Zugbrücke hoch|drawbridge up], [Fallgatter runter|portcullis down]!" if gh.closed else
                          "[Zugbrücke runter|drawbridge down], [Fallgatter hoch|portcullis up]!")
        elif k == "pechnase":
            from ..combat import siege as SIEGE
            gh = SIEGE.gatehouse_near(self, d.x)
            if gh is None:
                return False
            if p.inv.remove("pech", 1):
                SIEGE.pour_pitch(self, gh, by=p)
                self.sync_held()
            else:
                self.ui.toast("You need [Pech|pitch] to pour. (Ofen: 3 Holz + 1 Kohle)")
        else:
            return False
        return True

    def sleep(self):
        if not (self.env.is_night() or self.env.hour() > 19):
            self.ui.toast("You are not tired. [Schlafen|sleep] only at night.")
            return
        h = self.env.hour()
        add = ((24 - h) + 6) if h > 6 else (6 - h)
        self.env.time += add / 24 * DAY_LENGTH
        self.player.hp = self.player.max_hp
        from ..combat import injury as INJ
        INJ.rest(self.player, 8)
        self.player.spawn_x = self.player.cx
        self.ui.fade("[Gute Nacht|good night]… [Guten Morgen|good morning]!")
        self.renderer.light_cache = None

    def respawn(self):
        p = self.player
        p.dead = False
        p.hp = p.max_hp * 0.6
        p.injury.clear()
        p.wounds.clear()
        p.ragdoll = None
        p.pose.rot = 0.0
        p.state = "idle"
        p.hunger = max(p.hunger, 40)
        lost = p.inv.money // 3
        p.inv.money -= lost
        x = getattr(p, "spawn_x", None)
        if x is None:
            s = min(self.world.settlements, key=lambda s: abs((s["x0"] + s["x1"]) / 2 * TILE - p.cx))
            x = (s["x0"] + s["x1"]) / 2 * TILE
        tx = int(x // TILE)
        g = self.world.ground_at(tx, max(0, int(self.world.surface[tx]) - 3))
        p.x, p.y = x, g * TILE - p.h - 1
        p.vx = p.vy = 0
        p.fall_peak = p.y
        p.void_fall = 0
        self.camera.snap(p.cx, p.cy)
        self.ui.toast(f"You wake, robbed of {lost} [Pfennig|pennies]. [Gott sei Dank|thank God] you live.")

    # ================================================================== drawing
    def draw(self, screen):
        z = getattr(self, "zoom", 1.0)
        if z != 1.0:
            size = self.view_size()
            if self._view is None or self._view.get_size() != size:
                self._view = pygame.Surface(size).convert()
            self.draw_world(self._view)
            pygame.transform.smoothscale(self._view, screen.get_size(), screen)
        else:
            self.draw_world(screen)
        self.ui.draw(screen)

    def draw_world(self, surf):
        r = self.renderer
        cam = self.camera
        ox, oy = cam.offset()
        env = self.env
        SW, SH = surf.get_size()
        r.set_season(env.season_name()[0])
        r.time = env.time
        r.storm = env.rain() if env.current()[0] in ("sturm", "regen") else 0.0
        sun = env.sun_height()
        night = max(0.0, min(1.0, -sun * 3 + 0.3)) if sun < 0.1 else 0.0
        r.draw_sky(surf, env, cam)
        if getattr(self, "ambient", None) is not None:
            self.ambient.draw(surf, ox, oy, env)
        r.draw_parallax(surf, env, cam)
        r.draw_terrain(surf, cam)
        r.draw_buildings(surf, cam)
        r.draw_gatehouses(surf, cam)
        r.draw_decor(surf, cam, env.time, env.wind, night)
        r.draw_trees(surf, cam, env.time, env.wind)
        r.draw_objects(surf, cam)
        for x, y, proto, f, t in self.corpses:
            if -60 < x - ox < SW + 60:
                pygame.draw.ellipse(surf, (60, 40, 34), (x - ox - 12, y - oy - 5, 24, 5))
                pygame.draw.line(surf, proto.look["tunic"], (x - ox - 10, y - oy - 3), (x - ox + 8, y - oy - 4), 4)
        for b in self.boats:
            b.draw(surf, ox, oy)
        for e in self.engines:
            e.draw(surf, ox, oy, self)
        for hf in self.formations:
            hf.draw(surf, ox, oy, self.ui.small)
        # soft contact shadows under everyone standing on something
        from ..gfx import paint
        for a in self.animals:
            if getattr(a, "on_ground", False) and not a.dead and -60 < a.cx - ox < SW + 60:
                paint.contact_shadow(surf, a.cx - ox, a.feet - oy + 1, a.w * 1.25, 80)
        for h in self.humanoids:
            if h.on_ground and not h.dead and getattr(h, "mount", None) is None and -60 < h.cx - ox < SW + 60:
                paint.contact_shadow(surf, h.cx - ox, h.feet - oy + 1, 22, 85)
        for a in self.animals:
            a.draw(surf, ox, oy)
        for h in sorted(self.humanoids, key=lambda h: (h is self.player, not h.dead)):
            sx, sy = h.cx - ox, h.feet - oy
            if -60 < sx < SW + 60 and -80 < sy < SH + 80:
                draw_humanoid(surf, h, sx, sy)
                m = getattr(h, "mount", None)
                if m is not None and getattr(m, "_bit", None) is not None and not h.dead:
                    from ..gfx.rig import world_joints
                    J = world_joints(h)
                    hands = ("hb", "hf") if h.weapon_key == "fists" else ("hb",)
                    for k_ in hands:
                        hx, hy = J[k_]
                        pygame.draw.line(surf, (70, 46, 28), (hx - ox, hy - oy), m._bit, 1)
                if getattr(h, "carrying", None) is not None:
                    self.draw_carried(surf, h, ox, oy)
        r.draw_grass(surf, cam, env.time, env.wind)
        for d in self.drops:
            d.draw(surf, ox, oy)
        for pr in self.projectiles:
            pr.draw(surf, ox, oy)
        self.ctrl.draw_world(surf, ox, oy)
        r.draw_water(surf, cam, env.time)
        self.fx.draw(surf, ox, oy, self.ui.small, self.ui.tiny)
        lights = r.lights_in_view(cam, SW, SH, night)
        lights.append((self.player.cx, self.player.cy, 0.12))   # your eyes adjust to the dark a little
        for h in self.humanoids:
            ls = h.light_strength()
            if ls > 0 and abs(h.cx - self.player.cx) < 1400:
                lights.append((h.cx, h.y + 8, ls))
        w = self.world
        for pid in list(getattr(w, "burning", ()))[:60]:
            pc = w.pieces.get(pid)
            if pc is not None:
                lights.append((pc.cx, pc.cy, 0.9))
        for t in w.near("tree_chunks", ox - 200, ox + SW + 200):
            if t.burn > 0 and t.state == "stand":
                lights.append((t.x, t.y - t.h * 0.6, 1.0))
        for o in w.objects:
            if o.burn > 0:
                lights.append((o.x, o.y, 0.7))
        for pr in self.projectiles:
            if pr.fire:
                lights.append((pr.x, pr.y, 0.6))
        r.draw_lighting(surf, cam, env, lights)
        r.prewarm(cam, SW, SH)
        if getattr(self, "ambient", None) is not None:
            self.ambient.draw_front(surf, ox, oy)
        self.draw_weather(surf, ox, oy)
        self.ui.draw_world_overlays(surf, ox, oy)

    def draw_carried(self, surf, h, ox, oy):
        """Things too big for the bag are held in both arms in front of the chest."""
        from ..poly.render import draw_object
        o = h.carrying
        o.pos = (h.cx + h.facing * 8, h.y + 20)
        o.angle = 0.0 if o.kind == "log" or (max(abs(x) for x, _ in o.pts) > max(abs(y) for _, y in o.pts)) else 0.0
        draw_object(surf, o, ox, oy, self.renderer)

    def draw_weather(self, surf, ox, oy):
        env = self.env
        W, H = surf.get_size()
        rain = env.rain()
        p = self.player
        under = p.cy > self.world.surface[max(0, min(self.world.w - 1, int(p.cx // TILE)))] * TILE + 160
        if rain > 0.05 and not under:
            n = int(rain * 260)
            t = env.time
            snow = env.is_snowing()
            wind = env.wind
            rng = self._wrng = getattr(self, "_wrng", random.Random(3))
            rng.seed(int(t * 20))
            col = (200, 210, 230) if not snow else (245, 245, 250)
            for i in range(n):
                x = (i * 97.13 + t * (60 + wind * 300) * (0.3 if snow else 1.0) + ox * 0.0) % (W + 100) - 50
                y = (i * 53.71 + t * (520 if not snow else 70)) % (H + 40) - 20
                if snow:
                    surf.fill(col, (x + math.sin(t * 2 + i) * 6, y, 2, 2))
                else:
                    pygame.draw.line(surf, col, (x, y), (x - wind * 10, y + 12), 1)
        fog = env.fog()
        if fog > 0.02:
            s = pygame.Surface((W, H), pygame.SRCALPHA)
            s.fill((200, 204, 210, int(150 * fog)))
            surf.blit(s, (0, 0))
        if self.fx.flash > 0:
            s = pygame.Surface((W, H), pygame.SRCALPHA)
            s.fill((255, 255, 255, int(160 * self.fx.flash)))
            surf.blit(s, (0, 0))
            lb = getattr(self, "lightning_bolt", None)
            if lb and self.fx.flash > 0.6:
                x, y, _ = lb
                pts = [(x - ox, -10)]
                yy = -10
                rng = random.Random(int(x))
                while yy < y - oy:
                    yy += rng.randint(30, 70)
                    pts.append((x - ox + rng.randint(-25, 25), min(yy, y - oy)))
                if len(pts) >= 2:
                    pygame.draw.lines(surf, (255, 255, 240), False, pts, 3)
