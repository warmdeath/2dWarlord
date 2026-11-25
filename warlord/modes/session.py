"""A running game: world + simulation + entities + society + UI.

The Session owns everything and offers a small service API used by entities, brains, formations
and UI (targets_near, hostile, break_tile, fire_arrow, npc_say, ...). Systems never talk to each
other directly — they go through the session, which keeps the architecture modular.
"""
import math
import random

import pygame

from ..settings import TILE, SCREEN_W, SCREEN_H, SEA_LEVEL, DAY_LENGTH
from ..world import tiles as T
from ..world.weather import Environment
from ..world.worldsim import WorldSim, FallingBlock
from ..gfx.renderer import Renderer, Camera
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


class ItemDrop:
    kind = "drop"

    def __init__(self, key, n, x, y):
        self.key, self.n = key, n
        self.x, self.y = x, y
        self.vx = random.uniform(-40, 40)
        self.vy = -120
        self.removed = False
        self.t = 0.0
        self.uid = id(self)

    def update(self, game, dt):
        self.t += dt
        w = game.world
        p = game.player
        d = math.hypot(p.cx - self.x, p.cy - self.y)
        if self.t > 0.4 and d < 70 and not p.dead:
            self.x += (p.cx - self.x) * min(1, dt * 8)
            self.y += (p.cy - self.y) * min(1, dt * 8)
            if d < 16:
                left = p.inv.add(self.key, self.n)
                if left < self.n:
                    game.pickup_text(self.key, self.n - left)
                    game.emit("pickup", key=self.key, n=self.n - left)
                self.n = left
                if left <= 0:
                    self.removed = True
            return
        self.vy = min(500, self.vy + 900 * dt)
        nx, ny = self.x + self.vx * dt, self.y + self.vy * dt
        tx, ty = int(nx // TILE), int((ny + 5) // TILE)
        if w.inside(tx, ty) and (T.SOLID[w.fg[tx, ty]] or T.PLATFORM_T[w.fg[tx, ty]]):
            self.vy = 0
            self.vx *= 0.6
            ny = ty * TILE - 5
        self.x, self.y = nx, ny
        if self.t > 300 or self.y > w.pixel_h() + 200:
            self.removed = True

    def draw(self, surf, ox, oy):
        from ..ui.common import item_icon
        bob = math.sin(self.t * 4) * 2
        item_icon(surf, self.key, (self.x - ox - 12, self.y - oy - 14 + bob, 24, 24))


class Construction:
    def __init__(self, name, jobs):
        self.name = name
        self.jobs = jobs      # list of (x, y, fg, bg)
        self.i = 0
        self.acc = 0.0
        self.done = False


class Session:
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
        self.sim = WorldSim(self)
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
        for k in ("app", "renderer", "ui", "audio", "_view"):
            d[k] = None
        return d

    def restore(self, app):
        self.app = app
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
            for k, n in (("sichel", 1), ("bread", 3), ("seeds", 10)):
                inv.add(k, n)
            self.player.equip(weapon="fists")
            return
        for k, n in (("schwert", 1), ("spitzhacke", 1), ("axt", 1), ("bogen", 1), ("arrow", 40), ("torch", 10),
                     ("bread", 6), ("planks", 60), ("seeds", 10), ("holzschild", 1)):
            inv.add(k, n)
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
    def damage_tile(self, x, y, amount, by=None):
        w = self.world
        tid = int(w.fg[x, y])
        if tid == 0:
            return False
        td = T.TILES[tid]
        dmg = w.damage.get((x, y), 0.0) + amount
        if self.rng.random() < 0.15:
            self.fx.debris(x * TILE + 8, y * TILE + 8, td.color, 1)
        if dmg >= td.hardness:
            self.break_tile(x, y, drop=True, by=by)
            return True
        w.damage[(x, y)] = dmg
        return False

    def break_tile(self, x, y, drop=True, by=None):
        w = self.world
        tid = int(w.fg[x, y])
        if tid == 0:
            return
        td = T.TILES[tid]
        if tid == T.LOG.id:
            self.fell_tree(x, y, by)
            return
        if tid in (T.DOOR.id, T.DOOR_OPEN.id, T.GATE.id, T.GATE_OPEN.id):
            ys = [y]
            for d in (-1, 1):
                yy = y + d
                while w.inside(x, yy) and w.fg[x, yy] == tid:
                    ys.append(yy)
                    yy += d
            for yy in ys:
                w.set(x, yy, 0)
            if drop and td.drop:
                self.drop_item(td.drop, 1, x * TILE + 8, y * TILE + 8)
            self.sim.check_support(x, min(ys))
            return
        w.set(x, y, 0)
        w.fires.pop((x, y), None)
        self.fx.debris(x * TILE + 8, y * TILE + 8, td.color, 6)
        if drop:
            if tid == T.WHEAT4.id:
                self.drop_item("wheat", self.rng.randint(1, 3), x * TILE + 8, y * TILE + 8)
                self.drop_item("seeds", self.rng.randint(1, 2), x * TILE + 8, y * TILE + 8)
            elif tid == T.CHEST.id:
                for k, n in w.chests.pop((x, y), {}).items():
                    if n:
                        self.drop_item(k, n, x * TILE + 8, y * TILE + 8)
                self.drop_item("chest", 1, x * TILE + 8, y * TILE + 8)
            elif td.drop:
                self.drop_item(td.drop, 1, x * TILE + 8, y * TILE + 8)
        # grass under a removed plant? leaves the ground. Crops above farmland fall away.
        if w.inside(x, y - 1) and T.TILES[int(w.fg[x, y - 1])].deco and int(w.fg[x, y - 1]) not in (T.TORCH.id,):
            self.break_tile(x, y - 1, drop=drop, by=by)
        self.sim.check_support(x, y)
        if by is self.player:
            self.emit("break", tid=tid, x=x, y=y)

    def fell_tree(self, x, y, by=None):
        w = self.world
        # walk down to the base, then collect the connected trunk and crown
        base = y
        while w.inside(x, base + 1) and w.fg[x, base + 1] == T.LOG.id:
            base += 1
        stack = [(x, base)]
        seen = set()
        logs = 0
        while stack and len(seen) < 220:
            cx, cy = stack.pop()
            if (cx, cy) in seen or not w.inside(cx, cy):
                continue
            t = int(w.fg[cx, cy])
            if t not in (T.LOG.id, T.LEAVES.id, T.PINE.id):
                continue
            if cy > base:
                continue
            seen.add((cx, cy))
            if t == T.LOG.id:
                logs += 1
            for nx, ny in ((cx, cy - 1), (cx - 1, cy), (cx + 1, cy), (cx, cy + 1)):
                stack.append((nx, ny))
        for (cx, cy) in seen:
            t = int(w.fg[cx, cy])
            w.set(cx, cy, 0, wake=False)
            w.fires.pop((cx, cy), None)
            if self.rng.random() < 0.15:
                self.fx.debris(cx * TILE + 8, cy * TILE + 8, T.TILES[t].color, 2)
        if by is not None:
            self.drop_item("wood", max(1, logs), x * TILE + 8, base * TILE)
            if self.rng.random() < 0.6:
                self.drop_item("sapling", 1, x * TILE + 8, base * TILE)
        self.sfx("tree")
        if by is self.player:
            self.emit("chop", n=logs)

    def find_tree(self, tx, radius):
        w = self.world
        for d in range(4, radius):
            for x in (tx + d, tx - d):
                if not (0 <= x < w.w):
                    continue
                g = int(w.surface[x])
                for y in range(g - 2, g + 2):
                    if w.inside(x, y) and w.fg[x, y] == T.LOG.id and w.fg[x, y + 1] != T.LOG.id:
                        return (x, y)
        return None

    def try_place(self, p, key, tx, ty):
        w = self.world
        d = ITEMS[key]
        if not w.inside(tx, ty) or w.fg[tx, ty] != 0:
            return False
        tid = d.place
        td = T.TILES[tid]
        if td.solid:
            for h in self.humanoids + self.animals:
                if h.x < (tx + 1) * TILE and h.x + h.w > tx * TILE and h.y < (ty + 1) * TILE and h.feet > ty * TILE:
                    return False
        neighbours = [(tx + 1, ty), (tx - 1, ty), (tx, ty + 1), (tx, ty - 1)]
        if not any(w.inside(a, b) and (T.SOLID[w.fg[a, b]] or w.fg[a, b] in (T.LADDER.id, T.PLATFORM.id))
                   for a, b in neighbours) and not w.bg[tx, ty]:
            return False
        below = int(w.fg[tx, ty + 1]) if w.inside(tx, ty + 1) else 0
        if key == "seeds":
            if below in (T.GRASS.id, T.DIRT.id, T.MUD.id):
                w.set(tx, ty + 1, T.FARMLAND.id)
            elif below != T.FARMLAND.id:
                return False
        if key == "sapling" and below not in (T.GRASS.id, T.DIRT.id, T.SNOW.id, T.MUD.id):
            return False
        if td.deco and not T.SOLID[below] and not T.PLATFORM_T[below] and tid != T.TORCH.id:
            return False
        if key == "door":
            # doors are 3 tall
            if not all(w.inside(tx, ty - k) and w.fg[tx, ty - k] == 0 for k in (1, 2)):
                return False
            for k in range(3):
                w.set(tx, ty - k, T.DOOR.id)
        else:
            w.set(tx, ty, tid)
        if key == "chest":
            w.chests[(tx, ty)] = {}
        p.inv.remove(key, 1)
        self.sync_held()
        self.sfx("place")
        self.emit("place", key=key, x=tx, y=ty)
        return True

    def open_door(self, x, y):
        w = self.world
        ys = [yy for yy in range(y - 3, y + 4) if w.inside(x, yy) and w.fg[x, yy] == T.DOOR.id]
        for yy in ys:
            w.set(x, yy, T.DOOR_OPEN.id, wake=False)
        if ys:
            self.door_timers[(x, min(ys))] = (3.0, len(ys), T.DOOR.id)
            self.sfx("door")

    def can_open_gate(self, h, x, y):
        s = self.world.settlement_at(x, margin=4)
        if s is None:
            return True
        si = self.world.settlements.index(s)
        owner = self.society.owner.get(si, s["kingdom"])
        return not self.hostile_factions(h.faction, owner, h, None)

    def open_gate(self, x, y):
        w = self.world
        cols = [xx for xx in range(x - 2, x + 3) if any(w.inside(xx, yy) and w.fg[xx, yy] == T.GATE.id
                                                        for yy in range(y - 3, y + 4))]
        for xx in cols:
            ys = [yy for yy in range(y - 3, y + 4) if w.inside(xx, yy) and w.fg[xx, yy] == T.GATE.id]
            for yy in ys:
                w.set(xx, yy, T.GATE_OPEN.id, wake=False)
            if ys:
                self.door_timers[(xx, min(ys))] = (5.0, len(ys), T.GATE.id)
        self.sfx("gate")

    def update_doors(self, dt):
        w = self.world
        for key, (t, n, tid) in list(self.door_timers.items()):
            t -= dt
            if t > 0:
                self.door_timers[key] = (t, n, tid)
                continue
            x, y = key
            occupied = any(h.x < (x + 1) * TILE and h.x + h.w > x * TILE and h.y < (y + n) * TILE and h.feet > y * TILE
                           for h in self.humanoids + self.animals if not h.dead)
            if occupied:
                self.door_timers[key] = (1.0, n, tid)
                continue
            open_id = T.DOOR_OPEN.id if tid == T.DOOR.id else T.GATE_OPEN.id
            for yy in range(y, y + n):
                if w.inside(x, yy) and w.fg[x, yy] == open_id:
                    w.set(x, yy, tid, wake=False)
            del self.door_timers[key]

    # ================================================================== fire
    def ignite(self, x, y):
        w = self.world
        if w.inside(x, y) and T.FLAMMABLE[w.fg[x, y]] and (x, y) not in w.fires:
            w.fires[(x, y)] = 0.0
            return True
        return False

    def try_ignite_tile(self, x, y):
        if self.ignite(x, y):
            self.say_msg("[Feuer|fire]! The flames catch.")
            self.emit("ignite", x=x, y=y)

    def fire_near(self, px, py, r):
        tx, ty = int(px // TILE), int(py // TILE)
        best, bd = None, r * r
        for (x, y) in self.world.fires:
            d = (x - tx) ** 2 + (y - ty) ** 2
            if d < bd:
                best, bd = (x, y), d
        return best

    def extinguish(self, x, y):
        if self.world.fires.pop((x, y), None) is not None:
            self.fx.smoke(x * TILE + 8, y * TILE, 3)

    def settlement_produce(self, person, key, n):
        m = self.society.markets.get(person.settlement)
        if m is not None:
            m.stock[key] = m.stock.get(key, 0) + n

    # ================================================================== items
    def drop_item(self, key, n, x, y):
        if key and n > 0:
            self.drops.append(ItemDrop(key, n, x, y))

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
        h.say(line, t=4.5)
        if abs(h.cx - self.player.cx) < 300 and abs(h.cy - self.player.cy) < 200:
            self.hear(line, cat)

    def hear(self, line, ctx="", toast=True):
        new = self.player.dict.learn(line, ctx)
        if new and toast:
            self.ui.new_words(new)
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
        self.corpses.append([x, y, hf.protos[0], hf.facing, 0.0])
        if len(self.corpses) > 160:
            self.corpses.pop(0)
        self.fx.blood(x, y - 20, 5, -hf.facing)

    def hitstop(self, t):
        self.hitstop_t = max(self.hitstop_t, t)

    def sfx(self, name):
        if self.audio:
            self.audio.play(name)

    # ================================================================== LOD: people & animals
    def free_column(self, tx, g, direction=1, limit=40):
        """Nearest column to tx whose 3 tiles above row g are open (not inside a wall or tower)."""
        w = self.world
        for d in range(limit):
            for x in (tx + d * direction, tx - d * direction):
                if 0 <= x < w.w and not any(T.SOLID[w.fg[x, g - k]] for k in (1, 2, 3)):
                    return x
        return tx

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
            tx = self.free_column(int(x // TILE), p.g)
            x = tx * TILE + 8
            g = p.g if T.SOLID[self.world.fg[tx, p.g]] or T.PLATFORM_T[self.world.fg[tx, p.g]] else \
                self.world.ground_at(tx, max(0, p.g - 3))
            h = Humanoid(x - 7, g * TILE - 43, p.look, p.kingdom, p.name, p.rank)
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
                    if w.inside(tx, fy // TILE) and w.liq[tx, fy // TILE]:
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
        for b in self.boats:
            if abs(b.cx - p.cx) < 3000:
                b.update(self, dt)
        for pr in self.projectiles:
            pr.update(self, dt)
        for hf in self.formations:
            if not hf.dead:
                self.ai_command(hf, dt)
                hf.update(dt)
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
        self.sim.liquids(ptx)
        self.sim.fire(dt)
        self.sim.random_ticks(dt, ptx)
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

    def lightning_strike(self):
        w = self.world
        p = self.player
        tx = int(p.cx // TILE) + self.rng.randint(-40, 40)
        if not (0 <= tx < w.w):
            return
        g = w.ground_at(tx, 0)
        self.fx.flash = 1.0
        self.camera.shake = 4
        self.sfx("thunder")
        self.lightning_bolt = (tx * TILE + 8, g * TILE, 0.25)
        for dy in range(-1, 2):
            if w.inside(tx, g + dy) and T.FLAMMABLE[w.fg[tx, g + dy]]:
                self.ignite(tx, g + dy)
        # trees are struck first
        for y in range(0, g):
            if w.fg[tx, y] in (T.LEAVES.id, T.PINE.id, T.LOG.id, T.THATCH.id):
                self.ignite(tx, y)
                break
        for h in self.targets_near(tx * TILE, 30):
            h.take_hit(self, None, 40, "blunt", 50, ("unblockable",), source_x=tx * TILE)

    def update_edges(self, dt):
        """The abyss crumbles: chunks of the brink break away when you're near (story world)."""
        w = self.world
        p = self.player
        if p.cx / TILE > w.abyss_w + 260:
            return
        self.crumble_t -= dt
        if self.crumble_t > 0:
            return
        self.crumble_t = self.rng.uniform(2, 6)
        x = w.abyss_w
        while x < w.w and not w.fg[x].any():
            x += 1
        col = w.fg[x]
        ys = [y for y in range(w.h) if col[y]]
        if not ys:
            return
        for y in ys[: self.rng.randint(3, 9)]:
            tid = int(w.fg[x, y])
            if tid != T.BEDROCK.id:
                w.set(x, y, 0)
                self.spawn_falling(x, y, tid)
        self.camera.shake = max(self.camera.shake, 1.5)

    def spawn_falling(self, x, y, tid):
        if len(self.falling) < 300:
            self.falling.append(FallingBlock(x, y, tid))

    # ================================================================== construction
    def queue_blueprint(self, bp, tx, g):
        """Run the builder on the real world, diff it, restore, then build it tile by tile."""
        w = self.world
        x0, x1 = tx - 6, tx + bp.width + 8
        y0, y1 = max(0, g - 46), min(w.h, g + 7)
        before_fg = w.fg[x0:x1, y0:y1].copy()
        before_bg = w.bg[x0:x1, y0:y1].copy()
        before_liq = w.liq[x0:x1, y0:y1].copy()
        chests = dict(w.chests)
        bp.build(w, tx, g, self.rng)
        after_fg = w.fg[x0:x1, y0:y1].copy()
        after_bg = w.bg[x0:x1, y0:y1].copy()
        w.fg[x0:x1, y0:y1] = before_fg
        w.bg[x0:x1, y0:y1] = before_bg
        w.liq[x0:x1, y0:y1] = before_liq
        new_chests = {k: v for k, v in w.chests.items() if k not in chests}
        w.chests = chests
        jobs = []
        import numpy as np
        for lx, ly in np.argwhere((after_fg != before_fg) | (after_bg != before_bg)):
            jobs.append((x0 + int(lx), y0 + int(ly), int(after_fg[lx, ly]), int(after_bg[lx, ly])))
        # foundations first, then bottom-up
        jobs.sort(key=lambda j: (-j[1], j[0]))
        c = Construction(bp.de, jobs)
        c.chests = new_chests
        self.constructions.append(c)
        return len(jobs)

    def update_constructions(self, dt):
        w = self.world
        for c in self.constructions:
            c.acc += dt * 26
            while c.acc >= 1 and c.i < len(c.jobs):
                c.acc -= 1
                x, y, f, b = c.jobs[c.i]
                c.i += 1
                if w.fg[x, y] != f:
                    w.set(x, y, f)
                    if f and self.rng.random() < 0.3:
                        self.fx.dust(x * TILE + 8, y * TILE + 8, 2, (200, 180, 140))
                if w.bg[x, y] != b:
                    w.set_bg(x, y, b)
            if c.i >= len(c.jobs) and not c.done:
                c.done = True
                w.chests.update(c.chests)
                self.ui.toast(f"[Fertig|finished]: {c.name}")
                self.player.stats["built"] += 1
                self.emit("built", name=c.name)
        self.constructions = [c for c in self.constructions if not c.done]

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
        # tiles around the player
        tx0, ty0 = int(p.cx // TILE), int(p.cy // TILE)
        cands = []
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                x, y = tx0 + dx, ty0 + dy
                if w.inside(x, y) and w.fg[x, y]:
                    cands.append((abs(dx) + abs(dy), x, y, int(w.fg[x, y])))
        cands.sort()
        for _, x, y, tid in cands:
            if tid == T.DOOR.id:
                self.open_door(x, y)
                return
            if tid == T.DOOR_OPEN.id:
                for k in list(self.door_timers):
                    if k[0] == x:
                        self.door_timers[k] = (0.0, *self.door_timers[k][1:])
                return
            if tid == T.GATE.id:
                if self.can_open_gate(p, x, y):
                    self.open_gate(x, y)
                else:
                    self.ui.toast("The [Tor|gate] is barred against you.")
                return
            if tid == T.SIGN.id:
                txt = w.signs.get((x, y), "…")
                self.ui.toast("[Wegweiser|signpost]: " + txt.replace("\n", "   "), 7)
                return
            if tid == T.CHEST.id:
                c = w.chests.get((x, y), {})
                got = [(k, n) for k, n in c.items() if n]
                if not got:
                    self.ui.toast("The [Truhe|chest] is [leer|empty].")
                else:
                    s = self.world.settlement_at(x, margin=2)
                    for k, n in got:
                        p.inv.add(k, n)
                        self.pickup_text(k, n)
                    w.chests[(x, y)] = {}
                    if s is not None and self.rng.random() < 0.5:
                        witnesses = [h for h in self.humanoids if getattr(h, "person", None) and not h.dead and
                                     abs(h.cx - p.cx) < 200 and h is not p]
                        if witnesses:
                            self.npc_say(witnesses[0], "thief")
                            p.ehre -= 3
                            self.ui.toast("[Dieb|thief]! −3 [Ehre|honour]")
                return
            if tid == T.BED.id:
                self.sleep()
                return
            if tid == T.WHEAT4.id:
                self.break_tile(x, y, drop=True, by=p)
                if w.fg[x, y + 1] == T.FARMLAND.id:
                    w.set(x, y, T.WHEAT1.id)
                return
            if tid == T.ALTAR.id:
                if getattr(p, "prayed_day", -1) != self.env.day:
                    p.prayed_day = self.env.day
                    p.ehre += 1
                    self.ui.toast("You pray. [Amen|amen]. +1 [Ehre|honour]")
                else:
                    self.ui.toast("[Gott|God] has heard you today already.")
                return
            if tid == T.WELL.id:
                p.hunger = min(100, p.hunger + 3)
                self.ui.toast("Fresh [Wasser|water] from the [Brunnen|well].")
                return
            if tid in (T.WORKBENCH.id, T.ANVIL.id, T.FORGE.id, T.OVEN.id, T.LOOM.id, T.TABLE.id, T.FIRE_PIT.id):
                self.ui.open("inventory")
                return
            if tid == T.THRONE.id:
                self.ui.toast("The [Thron|throne]. Sitting on it uninvited would be… unwise.")
                return

    def sleep(self):
        if not (self.env.is_night() or self.env.hour() > 19):
            self.ui.toast("You are not tired. [Schlafen|sleep] only at night.")
            return
        h = self.env.hour()
        add = ((24 - h) + 6) if h > 6 else (6 - h)
        self.env.time += add / 24 * DAY_LENGTH
        self.player.hp = self.player.max_hp
        self.player.spawn_x = self.player.cx
        self.ui.fade("[Gute Nacht|good night]… [Guten Morgen|good morning]!")
        self.renderer.light_cache = None

    def respawn(self):
        p = self.player
        p.dead = False
        p.hp = p.max_hp * 0.6
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
        r.draw_sky(surf, env, cam)
        r.draw_parallax(surf, env, cam)
        r.draw_terrain(surf, cam)
        self.draw_fires_back(surf, ox, oy)
        for c in self.constructions:
            self.draw_scaffold(surf, c, ox, oy)
        sw = surf.get_width()
        for x, y, proto, f, t in self.corpses:
            if -60 < x - ox < sw + 60:
                pygame.draw.ellipse(surf, (60, 40, 34), (x - ox - 12, y - oy - 5, 24, 5))
                pygame.draw.line(surf, proto.look["tunic"], (x - ox - 10, y - oy - 3), (x - ox + 8, y - oy - 4), 4)
        for b in self.boats:
            b.draw(surf, ox, oy)
        for hf in self.formations:
            hf.draw(surf, ox, oy, self.ui.small)
        for a in self.animals:
            a.draw(surf, ox, oy)
        for h in sorted(self.humanoids, key=lambda h: (h is self.player, not h.dead)):
            sx, sy = h.cx - ox, h.feet - oy + h.step_smooth
            if -60 < sx < sw + 60 and -80 < sy < surf.get_height() + 80:
                draw_humanoid(surf, h, sx, sy)
        for d in self.drops:
            d.draw(surf, ox, oy)
        for fb in self.falling:
            fb.draw(surf, ox, oy)
        for pr in self.projectiles:
            pr.draw(surf, ox, oy)
        r.storm = env.rain() if env.current()[0] in ("sturm", "regen") else 0.0
        r.draw_liquids(surf, cam, env.time)
        self.draw_fires_front(surf, ox, oy)
        self.fx.draw(surf, ox, oy, self.ui.small, self.ui.tiny)
        lights = []
        for h in self.humanoids:
            ls = h.light_strength()
            if ls > 0 and abs(h.cx - self.player.cx) < 1400:
                lights.append((h.cx, h.y + 8, ls))
        for (x, y) in list(self.world.fires.keys())[:200]:
            lights.append((x * TILE + 8, y * TILE + 8, 0.9))
        for pr in self.projectiles:
            if pr.fire:
                lights.append((pr.x, pr.y, 0.6))
        r.draw_lighting(surf, cam, env, lights)
        self.draw_weather(surf, ox, oy)
        self.ui.draw_world_overlays(surf, ox, oy)

    def draw_scaffold(self, surf, c, ox, oy):
        for x, y, f, b in c.jobs[c.i:c.i + 400:3]:
            if f:
                pygame.draw.rect(surf, (210, 190, 140), (x * TILE - ox, y * TILE - oy, TILE, TILE), 1)

    def draw_fires_back(self, surf, ox, oy):
        pass

    def draw_fires_front(self, surf, ox, oy):
        t = self.env.time
        for (x, y), age in self.world.fires.items():
            px, py = x * TILE - ox, y * TILE - oy
            if -20 < px < surf.get_width() + 20 and -40 < py < surf.get_height() + 20:
                h = 10 + math.sin(t * 13 + x * 3) * 4
                pygame.draw.polygon(surf, (240, 110, 30), [(px, py + 16), (px + 8, py + 16 - h - 6), (px + 16, py + 16)])
                pygame.draw.polygon(surf, (255, 210, 90), [(px + 4, py + 16), (px + 8, py + 10 - h * 0.4),
                                                           (px + 12, py + 16)])
                if self.rng.random() < 0.05:
                    self.fx.smoke(x * TILE + 8, y * TILE - 4)
                if self.rng.random() < 0.06:
                    self.fx.fire(x * TILE + 8, y * TILE + 8, 1)

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
