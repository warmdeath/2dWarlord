"""How people act on the polygon world: the services the session offers to the player, NPC brains,
formations and siege code.

Interactions are deliberately few and physical:
  * fell trees (the trunk topples on its stump), buck the trunk into logs, carry logs in your arms
  * break structures piece by piece (what loses its support falls as rigid bodies)
  * place what you made (loose, or fixed in place: a door in a frame, stakes as a barrier, a plank bridge)
  * go underground: caves, ore veins in their walls, mine galleries
plus doors, fire, fields and the things lying around.
"""
import math
import random

import pygame

from ..settings import TILE, SEA_LEVEL
from ..items.items import ITEMS
from ..poly import prefab as PF
from ..poly.objects import PhysObject, objects_near, area
from ..poly.materials import MATS
from ..poly.world import Q_SOLID


CROP_ITEM = {"wheat": "wheat", "rye": "rye", "oat": "oats", "flax": "flax", "turnip": "turnip"}
CROP_SEED = {"wheat": "seeds", "rye": "seeds_rye", "oat": "seeds_oat", "flax": "seeds_flax", "turnip": "seeds_turnip"}
SEED_CROP = {v: k for k, v in CROP_SEED.items()}
# season index 0..3 (Frühling, Sommer, Herbst, Winter): how fast each crop grows (per day)
GROWTH = {"wheat": (0.25, 0.35, 0.1, 0.0), "rye": (0.3, 0.3, 0.15, 0.03), "oat": (0.3, 0.35, 0.1, 0.0),
          "flax": (0.3, 0.4, 0.05, 0.0), "turnip": (0.25, 0.3, 0.3, 0.05)}


class ItemDrop:
    kind = "drop"

    def __init__(self, key, n, x, y, quality=None):
        self.key, self.n = key, n
        self.x, self.y = x, y
        self.vx = random.uniform(-40, 40)
        self.vy = -120
        self.removed = False
        self.t = 0.0
        self.uid = id(self)
        self.quality = quality

    def update(self, game, dt):
        self.t += dt
        w = game.world
        p = game.player
        d = math.hypot(p.cx - self.x, p.cy - self.y)
        if self.t > 0.4 and d < 70 and not p.dead:
            self.x += (p.cx - self.x) * min(1, dt * 8)
            self.y += (p.cy - self.y) * min(1, dt * 8)
            if d < 16:
                left = p.inv.add(self.key, self.n, quality=self.quality)
                if left < self.n:
                    game.pickup_text(self.key, self.n - left)
                    game.emit("pickup", key=self.key, n=self.n - left)
                    self.n = left
                    if left <= 0:
                        self.removed = True
                    return
                # the bag is full: the thing stays on the ground
                if not getattr(game, "_full_warned", 0) or game.env.time - game._full_warned > 20:
                    game._full_warned = game.env.time
                    game.ui.toast("Your [Rucksack|bag] is full — too heavy for more.", 2.5)
                self.t = -2.0
                self.vx = (self.x - p.cx) * 2
            return
        self.vy = min(500, self.vy + 900 * dt)
        nx, ny = self.x + self.vx * dt, self.y + self.vy * dt
        if self.vy > 0 and w.solid_point(nx, ny + 5):
            gy = w.ground_y(nx, self.y - 2, 30)
            self.vy = 0
            self.vx *= 0.6
            ny = min(ny, gy - 5)
        wl = w.water_level(nx)
        if wl is not None and ny > wl:
            self.vy = min(self.vy, 40)
            self.vx *= 0.95
        self.x, self.y = nx, ny
        if self.t > 300 or self.y > w.pixel_h() + 200:
            self.removed = True

    def draw(self, surf, ox, oy):
        from ..ui.common import item_icon
        bob = math.sin(self.t * 4) * 2
        item_icon(surf, self.key, (self.x - ox - 12, self.y - oy - 14 + bob, 24, 24))


class Construction:
    def __init__(self, name, pieces, decor, ladders, bld):
        self.name = name
        self.pieces = pieces        # piece ids in build order
        self.decor = decor
        self.ladders = ladders
        self.bld = bld
        self.i = 0
        self.acc = 0.0
        self.done = False
        self.jobs = []


class WorldOps:
    # ================================================================== the physics tick
    def world_tick(self, dt):
        w = self.world
        p = self.player
        self._stream_t = getattr(self, "_stream_t", 0.0) - dt
        if self._stream_t <= 0:
            self._stream_t = 0.25
            cx = p.mount.cx if p.mount is not None else p.cx
            w.stream(cx, 2700)
            if self.battle is not None or self.formations:
                for hf in self.formations[:6]:
                    if abs(hf.x - cx) > 2000:
                        w.stream(hf.x, 600)
        w.wind = self.env.wind
        w.step(dt)
        w.earth.update(dt, p.mount.cx if p.mount is not None else p.cx)
        hits = getattr(w.space, "impacts", None)
        if hits:
            for e, ke in hits[:8]:
                if getattr(e, "dead", True) or getattr(e, "invuln", 0) > 0:
                    continue
                dmg = min(80.0, (ke - 2.0e6) / 1.2e5)
                if dmg > 4:
                    e.take_hit(self, None, dmg, "blunt", dmg, ("unblockable",), source_x=e.cx - 1)
            hits.clear()
        for o in list(w.objects):
            if abs(o.x - p.cx) < 3200 or o.crown is not None:
                o.update(self, dt)
        self.fire_tick(dt)
        self.update_doors(dt)
        for t in w.near("tree_chunks", p.cx - 1600, p.cx + 1600):
            if t.shake > 0:
                t.shake = max(0.0, t.shake - dt * 3)

    # ================================================================== hitting the world
    def hit_world(self, h, x, y, dmg, dtype="cut", tool=None):
        """A swing or a tool lands at (x, y). Returns True if it struck something of the world."""
        w = self.world
        wd = h.weapon_def
        key = tool or wd.key
        # a tree?
        for t in w.near("tree_chunks", x - 80, x + 80):
            if t.state == "stand" and self._on_tree(t, x, y):
                mult = {"axt": 1.0, "hellebarde": 0.5, "schwert": 0.15, "langschwert": 0.2}.get(key, 0.08)
                self.chop_tree(t, dmg * mult, h)
                return True
        # a log or loose piece?
        for o in objects_near(w, x, y, 8):
            if o.shape is not None and o.shape.point_query((x, y)).distance < 4:
                if o.kind == "log" and key in ("axt", "hellebarde") and o.crown is None:
                    self.buck_log(o, x, y, h)
                elif o.body is not None and not o.anchored:
                    o.body.apply_impulse_at_world_point((h.facing * dmg * 30, -dmg * 10), (x, y))
                    o.hp -= dmg * 0.3
                    if o.hp <= 0 and area(o.pts) < 900:
                        self.drop_item(o.item, 1, o.x, o.y)
                        o.remove()
                else:
                    o.hp -= dmg * 0.5
                    if o.hp <= 0:
                        self.drop_item(o.item or o.shape_key, 1, o.x, o.y)
                        o.remove()
                self.sfx("hit_wood")
                return True
        # an ore vein?
        for ore in w.ores:
            if ore["left"] > 0 and abs(ore["x"] - x) < 14 and abs(ore["y"] - y) < 14:
                self.mine_ore(ore, dmg * (1.0 if key == "spitzhacke" else 0.15), h)
                return True
        # a building piece?
        pc = PF.piece_at(w, x, y, solid_only=False)
        if pc is not None and pc.role not in ("backwall", "back", "gable", "window", "spandrel", "doorframe",
                                               "gate_back", "rail", "ladder"):
            hard = MATS[pc.mat].hard
            mult = {"hammer": 2.2, "spitzhacke": 2.0, "axt": 1.4 if pc.mat in MATS and MATS[pc.mat].flammable else 0.4,
                    "streitkolben": 0.8, "flegel": 0.5}.get(key, 0.25)
            self.damage_piece(pc, dmg * mult / max(0.3, hard), by=h)
            return True
        # loose earth: scoop it up
        if key in ("spitzhacke", "schaufel", "hacke", "fists") and math.hypot(x - h.cx, y - h.cy) < 100 and \
                w.earth.near(x, y, 6):
            return self.scoop(h, x, y, key)
        # the ground itself: dig
        if w.terrain_solid(x, y) and key in ("spitzhacke", "schaufel", "hacke", "fists") and \
                math.hypot(x - h.cx, y - h.cy) < 100:
            return self.dig(h, x, y, key)
        return False

    # ================================================================== digging
    SOIL_DEPTH = 70.0

    def dig(self, h, x, y, tool):
        """A pick or a shovel takes a ragged bite out of the ground and throws the earth out as loose clods,
        which pile up beside the hole (dig into them to scoop them into the bag)."""
        from shapely.geometry import Polygon
        w = self.world
        depth = y - w.surface_y(x)
        rock = depth > self.SOIL_DEPTH + 26 * math.sin(x * 0.0061)
        r = {"schaufel": (15, 6), "spitzhacke": (11, 10), "hacke": (9, 4), "fists": (6, 0)}[tool][1 if rock else 0]
        if r <= 0:
            self.ui.toast("Solid [Fels|rock]: you need a [Spitzhacke|pickaxe].", 2)
            return True
        # an irregular bite, a little wider than deep, ragged at the rim
        rng = self.rng
        n = 11
        a0 = rng.uniform(0, math.tau)
        pts = []
        for i in range(n):
            a = a0 + math.tau * i / n
            rr = r * rng.uniform(0.78, 1.12)
            pts.append((x + math.cos(a) * rr * 1.15, y + math.sin(a) * rr * 0.9))
        hole = Polygon(pts).buffer(1.5, quad_segs=2)
        area = w.dig(x, y, r, hole)
        if area <= 1:
            return False
        w.stream(self.player.cx, 2700)
        bio = w.biome_at(int(x // TILE))
        kind = "rock" if rock else ("sand" if bio in ("coast", "ocean", "islet") else "soil")
        col = (150, 146, 140) if rock else (118, 86, 58)
        # the earth flies off the blade, away from the digger and up out of the hole
        if tool == "schaufel":
            # a shovel lifts the earth out over the far rim and tosses it onto a heap beyond the hole
            fx = x + h.facing * r * 1.1
            sy = min(y - r * 0.3, w.surface_y(fx) - 8)
            w.earth.spawn(fx, sy, area, kind, h.facing * 1.4, r * 0.4, lift=1.2)
        else:
            # a pick breaks it loose where it is
            w.earth.spawn(x, y - r * 0.3, area, kind, rng.uniform(-0.4, 0.4), r * 0.6)
        self.fx.dust(x, y, 3, col)
        self.sfx("hit_stone" if rock else "dig")
        # ore next to the bite?
        for ore in w.ores:
            if ore["left"] > 0 and abs(ore["x"] - x) < r + 10 and abs(ore["y"] - y) < r + 10:
                self.mine_ore(ore, 25, h)
        # whatever stood on that ground may have lost its footing
        self.check_footing(x, y, r)
        if h is self.player:
            self.emit("dig", x=x, y=y)
        return True

    def scoop(self, h, x, y, tool):
        """Dig into loose earth: the clods go into the bag (380 units of area make one load)."""
        w = self.world
        r = {"schaufel": 16, "spitzhacke": 9, "hacke": 11, "fists": 7}.get(tool, 8)
        area, kind = w.earth.take(x, y, r)
        if area <= 0:
            return False
        bio = w.biome_at(int(x // TILE))
        item = "stone" if kind == "rock" else ("sand" if kind == "sand" else ("clay" if bio == "vineyard" else "dirt"))
        h.dug_area = getattr(h, "dug_area", 0.0) + area
        while h.dug_area >= 380:
            h.dug_area -= 380
            if h is self.player and self.player.inv.add(item, 1):
                self.drop_item(item, 1, x, y - 8)          # the bag is full: it lands at your feet
            elif h is self.player:
                self.pickup_text(item, 1)
        self.sfx("dig")
        return True

    def check_footing(self, x, y, r):
        w = self.world
        touched = set()
        for pid in list(w.near("piece_chunks", x - r - 80, x + r + 80)):
            pc = w.pieces.get(pid)
            if pc is None or not pc.grounded or pc.state != "static" or pc.role in ("pier", "found"):
                continue
            x0, y0, x1, y1 = pc.bb
            if x1 < x - r - 2 or x0 > x + r + 2 or abs(y1 - y) > r + 8:
                continue
            xs = [x0 + 2 + (x1 - x0 - 4) * k / 4 for k in range(5)]
            if not any(w.terrain_solid(xx, y1 + 3) for xx in xs):
                pc.grounded = False
                touched.add(pc.bld)
        for bid in touched:
            b = PF.building(w, bid)
            if b is not None and PF.settle(w, b):
                self.camera.shake = max(self.camera.shake, 3)
                self.sfx("collapse")
        # trees lose their roots
        for t in w.near("tree_chunks", x - r - 20, x + r + 20):
            if t.state == "stand" and abs(t.x - x) < r and abs(t.y - y) < r + 6 and not w.terrain_solid(t.x, t.y + 4):
                self.fell_tree(t)

    TOOL_PREF = {"fell": ("axt", "hellebarde"), "cut": ("axt", "hellebarde"), "mine": ("spitzhacke",),
                 "dig": ("schaufel", "spitzhacke", "hacke"), "break_wood": ("axt", "hammer", "spitzhacke"),
                 "break": ("hammer", "spitzhacke", "streitkolben", "axt")}

    def world_action(self, h, x, y):
        """What is under the mouse that the hands can work on? -> (verb, tools, hit point) or None.
        Trees and trunks are reached by standing next to them, wherever on them you point."""
        w = self.world
        for t in w.near("tree_chunks", x - 90, x + 90):
            if t.state == "stand" and self._on_tree(t, x, y) and abs(t.x - h.cx) < t.tw / 2 + 70:
                return "fell", self.TOOL_PREF["fell"], (t.x - h.facing * 2, min(t.y - 14, h.y + 22))
        near_mouse = math.hypot(x - h.cx, y - h.cy) < 92
        for o in objects_near(w, x, y, 8):
            if o.shape is not None and o.shape.point_query((x, y)).distance < 5 and o.kind == "log" and \
                    abs(o.x - h.cx) < 140 and abs(o.y - h.cy) < 80:
                return "cut", self.TOOL_PREF["cut"], (x, y)
        if not near_mouse:
            return None
        for ore in w.ores:
            if ore["left"] > 0 and abs(ore["x"] - x) < 14 and abs(ore["y"] - y) < 14:
                return "mine", self.TOOL_PREF["mine"], (x, y)
        pc = PF.piece_at(w, x, y, solid_only=True)
        if pc is not None:
            v = "break_wood" if MATS[pc.mat].flammable else "break"
            return v, self.TOOL_PREF[v], (x, y)
        if w.earth.near(x, y, 6) or w.terrain_solid(x, y):
            return "dig", self.TOOL_PREF["dig"], (x, y)
        return None

    def best_tool_for(self, x, y):
        a = self.world_action(self.player, x, y)
        if a is None:
            return None, None
        verb, tools, _ = a
        inv = self.player.inv
        return next((t for t in tools if inv.count(t)), tools[0]), verb

    @staticmethod
    def _on_tree(t, x, y):
        """Generous hit area: the trunk and the lower half of the crown."""
        if abs(t.x - x) < t.tw / 2 + 12 and t.y - t.h * 0.7 < y < t.y + 6:
            return True
        return abs(t.x - x) < t.h * 0.22 and t.y - t.h * 0.95 < y < t.y - t.h * 0.45

    def damage_piece(self, pc, amount, by=None, impulse=None):
        w = self.world
        if pc.state != "static":
            return False
        pc.hp -= amount
        b = PF.building(w, pc.bld)
        if b is not None:
            b.version += 1
        m = MATS[pc.mat]
        if self.rng.random() < 0.5:
            self.fx.debris(pc.cx, pc.cy, m.color, 2)
        self.sfx(m.sound)
        if pc.hp <= 0:
            self.break_piece(pc, by=by, impulse=impulse)
            return True
        return False

    def break_piece(self, pc, by=None, drop=True, impulse=None):
        w = self.world
        m = MATS[pc.mat]
        self.fx.debris(pc.cx, pc.cy, m.color, 8)
        b = PF.remove_piece(w, pc)
        if drop and m.drop and self.rng.random() < 0.8:
            n = max(1, int(pc.area // 260))
            self.drop_item(m.drop, min(4, n), pc.cx, pc.cy)
        fallen = 0
        if b is not None:
            # hand-made pieces: break into rubble that tumbles out
            if pc.area > 300 and self.rng.random() < 0.7 and pc.solid:
                half = [(x - pc.cx, y - pc.cy) for x, y in pc.pts]
                o = PhysObject.spawn(w, [(x * 0.5, y * 0.5) for x, y in half], pc.cx, pc.cy, pc.mat, "debris",
                                     debris=True)
                if impulse:
                    o.body.apply_impulse_at_local_point(impulse, (0, 0))
            fallen = PF.settle(w, b)
            if fallen:
                self.camera.shake = max(self.camera.shake, min(6, 1 + fallen * 0.3))
                self.sfx("collapse")
            if b.rec is not None:
                b.rec["damaged"] = b.rec.get("damaged", 0) + 1
        if by is self.player:
            self.emit("break", mat=pc.mat, role=pc.role, x=pc.cx, y=pc.cy)
        return fallen

    # ================================================================== trees and logs
    def chop_tree(self, t, dmg, by=None):
        if t.state != "stand":
            return
        t.hp -= dmg
        t.shake = 1.0
        self.fx.debris(t.x, t.y - 20, (200, 170, 120), 3)
        self.sfx("chop")
        if t.hp <= 0:
            self.fell_tree(t, by)

    def fell_tree(self, t, by=None):
        """The trunk becomes a rigid body hinged on its stump; it tips over away from the axe."""
        import pymunk
        w = self.world
        L = t.h * 0.78
        th = max(6.0, t.tw * 0.9)
        base_y = t.y - 10
        cx, cy = t.x, base_y - L / 2
        o = PhysObject.log(w, cx, cy, L, th, angle=-math.pi / 2)
        o.crown = t
        o.n = max(2, int(L // 40))
        o.item = "wood"
        side = 1 if by is None or by.cx < t.x else -1
        o.body.angular_velocity = side * 0.35
        o.body.apply_impulse_at_local_point((0, side * o.body.mass * 30), (L / 2, 0))
        hinge = pymunk.PivotJoint(w.space.static_body, o.body, (t.x, base_y), (-L / 2, 0))
        hinge.max_force = 9e8
        w.space.add(hinge)
        o.hinge = hinge
        t.state = "stump"
        t.regrow = 0.0
        t.hp = t.max_hp
        self.sfx("tree")
        if by is self.player:
            self.emit("chop", n=o.n)
            self.say_msg("[Baum fällt|timber]!", 2.5)

    def tree_landed(self, o):
        t = o.crown
        o.crown = None
        tip = o.world_pts()[1]
        for _ in range(3):
            self.fx.debris(tip[0], tip[1], (90, 130, 60), 6)
        self.drop_item("wood", self.rng.randint(1, 3), tip[0], tip[1] - 10)
        if self.rng.random() < 0.6:
            self.drop_item("sapling", 1, tip[0], tip[1] - 10)
        if t.kind in ("oak", "beech") and self.rng.random() < 0.4:
            self.drop_item("berries" if t.kind != "oak" else "wood", 1, tip[0], tip[1] - 10)
        self.camera.shake = max(self.camera.shake, 3)
        self.sfx("collapse")
        # the falling trunk hits whatever stands where the crown lands
        for e in self.targets_near(tip[0], 50):
            if not e.dead and abs(e.cy - tip[1]) < 60:
                e.take_hit(self, None, 35, "blunt", 60, ("unblockable",), source_x=o.x)

    def buck_log(self, o, x, y, by=None):
        """Cut a lying trunk across where the axe struck: two shorter logs."""
        o.hp -= 30
        self.fx.debris(x, y, (196, 160, 108), 3)
        self.sfx("chop")
        if o.hp > 0:
            return False
        w = self.world
        b = o.body
        lx, ly = b.world_to_local((x, y))
        hl = o.pts[1][0]
        th = abs(o.pts[0][1]) + abs(o.pts[3][1])
        cut = max(-hl + 16, min(hl - 16, lx))
        pieces = [(-hl, cut), (cut, hl)]
        ang = b.angle
        c, s = math.cos(ang), math.sin(ang)
        px, py = b.position
        o.remove()
        for a0, a1 in pieces:
            L = a1 - a0
            mid = (a0 + a1) / 2
            wx, wy = px + mid * c, py + mid * s
            if L < 52:
                self.drop_item("wood", max(1, int(L // 26)), wx, wy - 6)
            else:
                PhysObject.log(w, wx, wy, L, th, angle=ang)
        if by is self.player:
            self.emit("buck")
        return True

    def find_tree(self, x, radius_tiles):
        best, bd = None, radius_tiles * TILE
        for t in self.world.near("tree_chunks", x * TILE - bd, x * TILE + bd):
            if t.state == "stand" and t.burn <= 0 and t.kind != "dead":
                d = abs(t.x - x * TILE)
                if 60 < d < bd:
                    best, bd = t, d
        return best

    def mine_ore(self, ore, dmg, by=None):
        ore["hp"] -= dmg
        col = {"coal": (40, 40, 44), "iron": (170, 110, 80), "silver": (220, 220, 230), "gold": (240, 200, 70),
               "salt": (236, 232, 226), "glutstein": (255, 120, 50)}.get(ore["kind"], (140, 130, 120))
        self.fx.debris(ore["x"], ore["y"], col, 3)
        self.sfx("hit_stone")
        if ore["hp"] <= 0:
            ore["hp"] = 40
            ore["left"] -= 1
            item = {"coal": "coal", "iron": "iron_ore", "silver": "silver_ore", "gold": "gold_ore", "salt": "salt",
                    "glutstein": "glutstein", "stone": "stone"}[ore["kind"]]
            self.drop_item(item, 1, ore["x"], ore["y"] - 6)
            if by is self.player:
                self.emit("mine", kind=ore["kind"])

    # ================================================================== doors
    def door_contact(self, e):
        """Walking into a door opens it (gates only for friends)."""
        pc = getattr(e, "blocked_by", None)
        if pc is None:
            return
        if isinstance(pc, PF.Piece) and pc.role == "door" and not pc.open:
            b = PF.building(self.world, pc.bld)
            if b is not None and b.kind in ("wall", "gatehouse") and not self.can_open_gate(e, int(pc.cx // TILE),
                                                                                             0):
                return
            self.open_door_piece(pc)
        elif isinstance(pc, PhysObject) and pc.shape_key == "door" and pc.anchored and not getattr(pc, "is_open",
                                                                                                     False):
            self.toggle_object_door(pc)

    def open_door_piece(self, pc, t=3.0):
        if pc.locked:
            return False
        PF.toggle_door(self.world, pc, True)
        self.door_timers[pc.id] = t
        self.sfx("door")
        return True

    def open_door(self, x, y):
        """Old tile-coordinate API: open the nearest door."""
        pc = self.door_near(x * TILE + 8, y * TILE + 8, 30)
        if pc is not None:
            self.open_door_piece(pc)

    def open_gate(self, x, y):
        self.open_door(x, y)

    def door_near(self, px, py, r):
        best, bd = None, r
        for pid in self.world.near("piece_chunks", px - r - 40, px + r + 40):
            pc = self.world.pieces.get(pid)
            if pc is not None and pc.role == "door":
                d = math.hypot(pc.cx - px, pc.cy - py)
                if d < bd:
                    best, bd = pc, d
        return best

    def update_doors(self, dt):
        w = self.world
        for pid, t in list(self.door_timers.items()):
            if not isinstance(pid, int):
                del self.door_timers[pid]
                continue
            t -= dt
            pc = w.pieces.get(pid)
            if pc is None:
                del self.door_timers[pid]
                continue
            if t > 0:
                self.door_timers[pid] = t
                continue
            x0, y0, x1, y1 = pc.bb
            occupied = any(e.x < x1 + 2 and e.x + e.w > x0 - 2 and e.y < y1 and e.feet > y0
                           for e in self.humanoids + self.animals if not e.dead)
            if occupied:
                self.door_timers[pid] = 1.0
                continue
            PF.toggle_door(w, pc, False)
            del self.door_timers[pid]

    def toggle_object_door(self, o):
        o.is_open = not getattr(o, "is_open", False)
        if o.shape is not None:
            o.shape.sensor = o.is_open
        self.sfx("door")

    # ================================================================== fire
    def ignite_at(self, x, y, r=12):
        w = self.world
        pc = PF.piece_at(w, x, y, pad=r)
        if pc is not None and MATS[pc.mat].flammable:
            return self.ignite_piece(pc)
        for t in w.near("tree_chunks", x - 60, x + 60):
            if t.state == "stand" and abs(t.x - x) < t.h * 0.3 and t.y - t.h < y < t.y + 5 and t.burn <= 0:
                t.burn = 0.01
                return True
        for o in objects_near(w, x, y, r):
            if MATS[o.mat].flammable and o.burn <= 0:
                o.burn = 0.01
                return True
        return False

    def ignite(self, x, y):
        """Old tile-coordinate API."""
        return self.ignite_at(x * TILE + 8, y * TILE + 8)

    def ignite_piece(self, pc):
        if pc.burn > 0 or not MATS[pc.mat].flammable or pc.state != "static":
            return False
        pc.burn = 0.01
        self.world.burning = getattr(self.world, "burning", set())
        self.world.burning.add(pc.id)
        return True

    def try_ignite_tile(self, x, y):
        if self.ignite_at(x * TILE + 8, y * TILE + 8, 16):
            self.say_msg("[Feuer|fire]! The flames catch.")
            self.emit("ignite", x=x, y=y)

    def fire_tick(self, dt):
        w = self.world
        burning = getattr(w, "burning", None)
        if burning is None:
            w.burning = burning = set()
        rain = self.env.rain() if self.env.is_raining() else 0.0
        for pid in list(burning):
            pc = w.pieces.get(pid)
            if pc is None or pc.state != "static":
                burning.discard(pid)
                continue
            pc.burn += dt
            pc.hp -= dt * (3.0 + pc.max_hp * 0.04)
            if self.rng.random() < dt * 3:
                self.fx.fire(pc.cx + self.rng.uniform(-pc.w / 2, pc.w / 2), pc.cy, 1)
            if self.rng.random() < dt * 1.5:
                self.fx.smoke(pc.cx, pc.bb[1], 1)
            if rain and self.rng.random() < dt * rain * 0.4:
                pc.burn = 0
                burning.discard(pid)
                self.fx.smoke(pc.cx, pc.cy, 3)
                continue
            if self.rng.random() < dt * 0.5:
                # spread to what touches it
                for q in pc.below + pc.side:
                    qq = w.pieces.get(q)
                    if qq is not None and self.rng.random() < 0.5:
                        self.ignite_piece(qq)
                b = PF.building(w, pc.bld)
                if b is not None:
                    for q in b.pieces:
                        qq = w.pieces.get(q)
                        if qq is not None and qq.solid and qq.bb[3] <= pc.bb[1] + 4 and abs(qq.cx - pc.cx) < 60 and \
                                self.rng.random() < 0.25:
                            self.ignite_piece(qq)
                for t in w.near("tree_chunks", pc.cx - 80, pc.cx + 80):
                    if t.state == "stand" and abs(t.x - pc.cx) < 60 and self.rng.random() < 0.2:
                        t.burn = max(t.burn, 0.01)
            for e in self.targets_near(pc.cx, 24):
                if not e.dead and e.y < pc.bb[3] and e.feet > pc.bb[1]:
                    e.hp -= 10 * dt
                    if e.hp <= 0:
                        e.die(self, None)
            if pc.hp <= 0:
                burning.discard(pid)
                self.break_piece(pc, drop=False)
                if self.rng.random() < 0.5:
                    self.drop_item("coal", 1, pc.cx, pc.cy)
        p = self.player
        for t in w.near("tree_chunks", p.cx - 1800, p.cx + 1800):
            if t.burn > 0 and t.state == "stand":
                t.burn += dt
                if self.rng.random() < dt * 4:
                    self.fx.fire(t.x + self.rng.uniform(-t.h * 0.25, t.h * 0.25), t.y - t.h * self.rng.uniform(0.4,
                                                                                                             0.9), 1)
                if self.rng.random() < dt * 0.3:
                    for t2 in w.near("tree_chunks", t.x - 120, t.x + 120):
                        if t2 is not t and t2.state == "stand" and abs(t2.x - t.x) < 90 and t2.burn <= 0:
                            t2.burn = 0.01
                if rain and self.rng.random() < dt * rain * 0.3:
                    t.burn = 0
                if t.burn > 25:
                    t.burn = 0
                    t.state = "stump"
                    t.kind = "dead" if t.kind not in ("pine", "fir") else t.kind
                    t._geo = None
                    self.drop_item("coal", 2, t.x, t.y - 10)
            elif t.state == "stump" and t.kind != "dead":
                t.regrow += dt / 900.0
                if t.regrow >= 1.0:
                    t.state = "stand"
                    t.regrow = 0.0
                    t.hp = t.max_hp
                    t._geo = None

    def fire_near(self, px, py, r):
        """The nearest burning thing within r tiles (people run to put it out)."""
        w = self.world
        best, bd = None, r * TILE
        for pid in getattr(w, "burning", ()):
            pc = w.pieces.get(pid)
            if pc is not None:
                d = math.hypot(pc.cx - px, pc.cy - py)
                if d < bd:
                    best, bd = ("piece", pid), d
        return best

    def fire_pos(self, ref):
        kind, pid = ref
        pc = self.world.pieces.get(pid)
        return (pc.cx, pc.cy) if pc is not None else None

    def is_burning(self, ref):
        kind, pid = ref
        pc = self.world.pieces.get(pid)
        return pc is not None and pc.burn > 0

    def extinguish(self, ref, y=None):
        if y is not None:     # old tile API
            pc = PF.piece_at(self.world, ref * TILE + 8, y * TILE + 8, pad=10)
            ref = ("piece", pc.id) if pc is not None else None
        if ref is None:
            return
        pc = self.world.pieces.get(ref[1])
        if pc is not None and pc.burn > 0:
            pc.burn = 0
            getattr(self.world, "burning", set()).discard(pc.id)
            self.fx.smoke(pc.cx, pc.cy, 3)

    # ================================================================== fields
    def plot_at(self, x):
        for i, pl in enumerate(self.world.plots):
            if pl.x0 <= x < pl.x1:
                return pl, pl.strip_at(x)
        return None, None

    def till(self, x, y=None):
        if y is not None and x < self.world.w:      # old tile API
            x = x * TILE + 8
        pl, st = self.plot_at(x)
        if st is not None:
            if not st[2]:
                st[2] = True
                self.fx.dust(x, pl.y, 4, (112, 78, 52))
                return True
            return False
        # break new ground: a fresh plot of one strip that grows as you keep tilling
        w = self.world
        gy = w.surface_y(x)
        if w.water_level(x) is not None or w.settlement_at(int(x // TILE)) and PF.piece_at(w, x, gy - 10):
            return False
        for pl in w.plots:
            if abs(pl.y - gy) < 10 and (abs(pl.x1 - x) < TILE or abs(pl.x0 - x) < TILE):
                if x >= pl.x1:
                    pl.x1 += TILE
                    pl.strips.append([None, 0.0, True, 1.0, 0.0])
                else:
                    pl.x0 -= TILE
                    pl.strips.insert(0, [None, 0.0, True, 1.0, 0.0])
                self._refresh_plot_decor(pl)
                self.fx.dust(x, gy, 4, (112, 78, 52))
                return True
        pl = PF.Plot(int(x // TILE) * TILE, int(x // TILE) * TILE + TILE, gy, None)
        pl.strips = [[None, 0.0, True, 1.0, 0.0]]
        w.plots.append(pl)
        d = PF.Decor("plot", (pl.x0 + pl.x1) / 2, gy, TILE, 8, plot=len(w.plots) - 1)
        w.index_add("decor_chunks", d.x, d)
        pl.decor = d
        self.fx.dust(x, gy, 4, (112, 78, 52))
        return True

    def _refresh_plot_decor(self, pl):
        w = self.world
        idx = w.plots.index(pl)
        for lst in w.decor_chunks.values():
            for d in lst:
                if d.kind == "plot" and d.data.get("plot") == idx:
                    lst.remove(d)
                    break
        d = PF.Decor("plot", (pl.x0 + pl.x1) / 2, pl.y, pl.x1 - pl.x0, 8, plot=idx)
        w.index_add("decor_chunks", d.x, d)

    def sow(self, x, seed_key):
        pl, st = self.plot_at(x)
        if st is None or not st[2]:
            self.ui.toast("Seeds need a tilled [Acker|field]: work the ground with a [Hacke|hoe] first.", 3)
            return False
        if st[0] is not None and st[1] > 0.02:
            return False
        st[0] = SEED_CROP.get(seed_key, "wheat")
        st[1] = 0.03
        return True

    def harvest(self, x, by=None):
        pl, st = self.plot_at(x)
        if st is None or st[0] is None or st[1] < 0.99:
            return False
        crop = st[0]
        fert = st[3]
        self.drop_item(CROP_ITEM[crop], max(1, int(round(1 + 2.2 * fert * self.rng.uniform(0.7, 1.2)))), x, pl.y - 10)
        self.drop_item(CROP_SEED[crop], self.rng.randint(1, 2), x, pl.y - 10)
        st[3] = max(0.15, fert - 0.25)          # every harvest tires the soil
        st[1] = 0.03 if st[3] >= 0.45 else 0.0  # Brache: tired soil is left fallow
        if st[1] == 0:
            st[0] = None
        self.fx.debris(x, pl.y - 8, (222, 190, 84), 4)
        return crop

    def manure(self, x, y=None):
        if y is not None and x < self.world.w:
            x = x * TILE + 8
        pl, st = self.plot_at(x)
        if st is not None and self.player.inv.remove("mist", 1):
            st[3] = min(1.5, st[3] + 0.5)
            self.fx.text(x, pl.y - 20, "Gedüngt", (180, 150, 90), gloss="manured")
            self.sync_held()
            return True
        return False

    def grow_crops(self, days=1.0):
        season = self.env.season()
        for pl in self.world.plots:
            for st in pl.strips:
                if st[0] is None:
                    st[3] = min(1.2, st[3] + 0.22 * days)       # fallow land recovers
                    continue
                st[3] = min(1.2, st[3] + 0.03 * days)
                g = GROWTH.get(st[0], (0.3, 0.3, 0.1, 0.0))[season] * (0.5 + 0.5 * min(1.0, st[3]))
                st[1] = min(1.0, st[1] + g * days)
                st[4] = max(0.0, st[4] - 0.5 * days)
                if season == 3 and st[1] < 1.0 and st[0] not in ("rye", "turnip"):
                    st[1] = max(0.0, st[1] - 0.2 * days)     # frost kills young shoots

    def trample(self, dt):
        """Running feet and hooves flatten growing crops — that's why villages build walkways over fields."""
        for e in list(self.humanoids) + list(self.animals):
            if e.dead or not e.on_ground or e.removed:
                continue
            speed = abs(e.mount.vx) if getattr(e, "mount", None) is not None else abs(e.vx)
            heavy = getattr(e, "species", "") in ("horse", "cow", "pig", "boar", "bear")
            if speed < (40 if heavy else 105):
                continue
            pl, st = self.plot_at(e.cx)
            if st is None or st[0] is None or abs(e.feet - pl.y) > 6:
                continue
            if st[1] >= 0.2 and st[4] < 0.5 and self.rng.random() < dt * 6:
                st[4] = 1.0
                st[1] = max(0.05, st[1] * 0.5)
                self.fx.debris(e.cx, pl.y - 4, (150, 170, 80), 3)
                if e is self.player or getattr(e, "rider", None) is self.player:
                    if not getattr(self, "_trample_warned", False):
                        self._trample_warned = True
                        self.ui.toast("[Zertrampelt|trampled]! The farmers won't thank you. Use the walkways.")
                    self.player.ehre -= 0 if self.rng.random() < 0.8 else 1
        p = self.player
        if p.mount is not None and p.inv.count("pflug") and p.intent.crouch:
            self.till(p.mount.cx)

    def farm_work(self, h, x):
        """A farmer works the strip at x: harvest what is ripe, sow what is bare. Returns produce or None."""
        pl, st = self.plot_at(x)
        if st is None:
            return None
        if st[0] is not None and st[1] >= 0.99:
            crop = st[0]
            st[3] = max(0.15, st[3] - 0.25)
            st[1] = 0.03 if st[3] >= 0.45 else 0.0
            if st[1] == 0:
                st[0] = None
            self.fx.debris(x, pl.y - 8, (222, 190, 84), 4)
            return {"oat": "oats"}.get(crop, crop)
        if st[0] is None and st[3] >= 0.7:
            p = getattr(h, "person", None)
            st[0] = getattr(p, "crop", None) or pl.crop or "wheat"
            st[1] = 0.03
            st[2] = True
        return None

    # ================================================================== items in the world
    def drop_item(self, key, n, x, y, quality=None):
        if key and n > 0 and key in ITEMS:
            self.drops.append(ItemDrop(key, n, x, y, quality))

    def pick_up(self, h, o):
        """Small things go into the bag; trunks, doors and beams are carried in the arms."""
        inv = h.inv
        a = area(o.pts)
        key = o.item if o.kind != "crafted" else o.shape_key
        if o.kind in ("log", "piece", "crafted", "debris") and o.anchored:
            return False
        if key and key in ITEMS and not inv.bulky(key) and a < 700 and o.kind != "log":
            if inv.add(key, max(1, o.n if o.kind != "crafted" else 1), quality=o.quality) == 0:
                o.remove()
                self.pickup_text(key, 1)
                return True
        if a > 5200 or o.mass() > 140:
            self.ui.toast("Too heavy to lift. [Zu schwer|too heavy] — cut it smaller first.", 2)
            return False
        if getattr(h, "carrying", None) is not None:
            return False
        o.detach()
        h.carrying = o
        self.sfx("pickup")
        return True

    def put_down(self, h, x=None, y=None, angle=None, anchor=False):
        o = getattr(h, "carrying", None)
        if o is None:
            return None
        h.carrying = None
        if x is None:
            x, y = h.cx + h.facing * (o.radius + 10), h.y + 10
        o.pos = (x, y)
        if angle is not None:
            o.angle = angle
        o.vel = (h.vx * 0.5, 0)
        o.avel = 0.0
        o.anchored = anchor
        o.removed = False
        w = self.world
        if o not in w.objects:
            w.objects.append(o)
        o.attach(w)
        if anchor:
            self.on_anchor(o)
        self.sfx("place")
        return o

    def throw(self, h):
        o = self.put_down(h)
        if o is not None and o.body is not None:
            o.body.velocity = (h.facing * 260, -160)
            o.body.angular_velocity = h.facing * 3

    def on_anchor(self, o):
        """A fixed object becomes part of the world: ladders climbable, doors usable."""
        if o.shape_key == "ladder" or o.item == "ladder":
            pts = o.world_pts()
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            if max(ys) - min(ys) > max(xs) - min(xs):
                r = (min(xs) - 4, min(ys), max(xs) + 4, max(ys))
                self.world.add_ladder(r)
                o.ladder_rect = r
                o.shape.sensor = True
        self.emit("place", key=o.shape_key or o.item, x=o.x, y=o.y)

    def place_item(self, p, key, x, y, angle=0.0, anchor=False):
        """Take something out of the bag and set it into the world as a physical object."""
        from ..items.shaping import TEMPLATES
        d = ITEMS.get(key)
        if d is None or not p.inv.count(key):
            return None
        if d.place == "fill" or (key in ("stone", "sand", "clay") and self.world.in_cave(x, y)):
            # empty a load of earth: loose clods that fall, settle and later set into the ground
            if self.world.terrain_solid(x, y) or PF.piece_at(self.world, x, y, solid_only=True):
                self.ui.toast("Tip the [Erde|earth] out where there is room.", 2)
                return None
            kind = "rock" if key == "stone" else "sand" if key == "sand" else "soil"
            self.world.earth.spawn(x, y, 380, kind, 0.0, 6)
            p.inv.remove(key, 1)
            self.sync_held()
            self.sfx("dig")
            return True
        if d.place == "seed":
            if self.sow(x, key):
                p.inv.remove(key, 1)
                self.sync_held()
                return True
            return None
        if d.place == "plant":
            gy = self.world.surface_y(x)
            if abs(gy - y) > 40 or PF.piece_at(self.world, x, gy - 8):
                return None
            from ..poly.flora import Tree
            t = Tree(self.rng.choice(["oak", "beech", "birch"]), x, gy + 3, self.rng.uniform(150, 210), 12,
                     self.rng.randint(0, 1 << 30))
            t.state = "stump"
            t.regrow = 0.05
            t.kind = t.kind
            self.world.trees.append(t)
            self.world.index_add("tree_chunks", x, t)
            p.inv.remove(key, 1)
            self.sync_held()
            return True
        shape = object_shape(key)
        o = PhysObject.spawn(self.world, shape, x, y, object_mat(key), "crafted", item=key, angle=angle,
                             quality=p.inv.quality.get(key, 0.7), shape_key=key)
        if anchor:
            o.anchor(True)
            self.on_anchor(o)
        p.inv.remove(key, 1)
        self.sync_held()
        self.sfx("place")
        return o

    # ================================================================== construction (blueprints)
    def queue_blueprint(self, bp, tx, g):
        """Lay out the building now, raise it piece by piece from the ground up."""
        w = self.world
        before = set(w.pieces)
        nb = len(w.buildings)
        bp.build(w, tx, g, self.rng)
        new = [w.pieces[i] for i in w.pieces if i not in before]
        for pc in new:
            w.piece_shape_removed(pc)
            pc.state = "planned"
        new.sort(key=lambda pc: (-pc.bb[3], pc.bb[0]))
        bld = w.buildings[nb] if len(w.buildings) > nb else None
        decor, ladders = [], []
        if bld is not None:
            decor = list(bld.decor)
            for d in decor:
                d.gone = True
            ladders = list(bld.ladders)
            for r in ladders:
                w.remove_ladder(r)
            bld.version += 1
        c = Construction(bp.de, [pc.id for pc in new], decor, ladders, bld)
        self.constructions.append(c)
        return len(new)

    def update_constructions(self, dt):
        w = self.world
        for c in self.constructions:
            c.acc += dt * 8
            while c.acc >= 1 and c.i < len(c.pieces):
                c.acc -= 1
                pc = w.pieces.get(c.pieces[c.i])
                c.i += 1
                if pc is not None and pc.state == "planned":
                    pc.state = "static"
                    w.piece_shape_added(pc)
                    if c.bld is not None:
                        c.bld.version += 1
                    if self.rng.random() < 0.4:
                        self.fx.dust(pc.cx, pc.cy, 2, (200, 180, 140))
                    self.sfx("place")
            if c.i >= len(c.pieces) and not c.done:
                c.done = True
                for d in c.decor:
                    d.gone = False
                for r in c.ladders:
                    w.add_ladder(r)
                self.ui.toast(f"[Fertig|finished]: {c.name}")
                self.player.stats["built"] += 1
                self.emit("built", name=c.name)
        self.constructions = [c for c in self.constructions if not c.done]

    # ================================================================== spawning on solid ground
    def free_spot(self, x, ground_y, direction=1, limit=600):
        """Nearest x near `x` where a person can stand on ground_y without being inside a wall."""
        w = self.world
        for d in range(0, limit, 6):
            for xx in (x + d * direction, x - d * direction):
                hits = w.space.bb_query(__import__("pymunk").BB(xx - 6, ground_y - 40, xx + 6, ground_y - 3), Q_SOLID)
                if not any(not h.sensor for h in hits) and not w.terrain_solid(xx, ground_y - 20):
                    return xx
        return x

    def free_column(self, tx, g, direction=1, limit=40):
        return int(self.free_spot(tx * TILE + 8, g * TILE, direction, limit * TILE) // TILE)

    # ================================================================== the world's edge crumbles
    def update_edges(self, dt):
        w = self.world
        p = self.player
        if p.cx / TILE > w.abyss_w + 260:
            return
        self.crumble_t -= dt
        if self.crumble_t > 0:
            return
        self.crumble_t = self.rng.uniform(3, 7)
        # find the brink: the first column with crust
        i = w.abyss_w
        while i < w.w and w.bottom[i] - w.top[i] < 4:
            i += 1
        if i >= w.w - 1 or i > w.abyss_w + 200:
            return
        x = i * TILE
        top, bot = float(w.top[i]), float(w.bottom[i])
        depth = min(bot - top, self.rng.uniform(40, 120))
        # the brink retreats by one column; what broke away tumbles into the void
        w.top[i] = w.bottom[i]
        w.set_surface(i, i + 1, [w.bottom[i]])
        pts = [(-8, -depth / 2), (8, -depth / 2 + self.rng.uniform(-4, 4)), (6, depth / 2), (-7, depth / 2)]
        o = PhysObject.spawn(w, pts, x + 8, top + depth / 2, "rock", "debris", debris=True)
        o.body.angular_velocity = self.rng.uniform(-1, 1)
        self.camera.shake = max(self.camera.shake, 1.5)
        for t in w.near("tree_chunks", x - 20, x + 20):
            if abs(t.x - x - 8) < 10 and t.state == "stand":
                self.fell_tree(t)

    # ================================================================== lightning
    def lightning_strike(self):
        w = self.world
        p = self.player
        x = p.cx + self.rng.randint(-40, 40) * TILE
        if not (0 <= x < w.pixel_w()):
            return
        # the tallest thing around is struck: a tree, a tower, a roof
        target_y = w.surface_y(x)
        best = None
        for t in w.near("tree_chunks", x - 200, x + 200):
            if t.state == "stand" and (best is None or t.y - t.h < best[1]):
                best = (t.x, t.y - t.h, t)
        for pid in w.near("piece_chunks", x - 200, x + 200):
            pc = w.pieces.get(pid)
            if pc is not None and pc.solid and pc.role in ("roof", "merlon", "plate") and (
                    best is None or pc.bb[1] < best[1]):
                best = (pc.cx, pc.bb[1], pc)
        self.fx.flash = 1.0
        self.camera.shake = 4
        self.sfx("thunder")
        if best is not None:
            bx, by, obj = best
            self.lightning_bolt = (bx, by, 0.25)
            if isinstance(obj, PF.Piece):
                if MATS[obj.mat].flammable:
                    self.ignite_piece(obj)
                else:
                    self.damage_piece(obj, obj.max_hp * 0.6)
            else:
                obj.burn = 0.01
            x = bx
        else:
            self.lightning_bolt = (x, target_y, 0.25)
        for h in self.targets_near(x, 30):
            h.take_hit(self, None, 40, "blunt", 50, ("unblockable",), source_x=x)


# ====================================================================== shapes of placeable things
def object_shape(key):
    from ..items.shaping import TEMPLATES
    for tk, t in TEMPLATES.items():
        if t[0] == key:
            poly = t[3]
            lo, hi = t[4]
            L = (lo + hi) / 2
            from shapely import affinity
            p = affinity.scale(poly, L, L, origin=(0, 0))
            p = p.convex_hull if key not in ("ladder", "stool", "trough", "bowl") else p
            pts = list(p.exterior.coords)[:-1]
            cx = sum(x for x, _ in pts) / len(pts)
            cy = sum(y for _, y in pts) / len(pts)
            if key in ("door", "ladder", "stake", "spike"):
                pts = [(y - cy, -(x - cx)) for x, y in pts]       # stand them up
            else:
                pts = [(x - cx, y - cy) for x, y in pts]
            return pts
    sizes = {"chest": (26, 18), "barrel": (16, 22), "table": (40, 20), "bed": (40, 14), "workbench": (44, 22),
             "anvil": (24, 16), "forge": (32, 30), "campfire": (22, 8), "oven": (30, 30), "loom": (34, 34),
             "fachwerk": (32, 32), "palisade": (10, 64), "platform": (64, 6), "planks": (64, 6), "stone": (14, 10),
             "brick": (16, 8), "wood": (40, 10), "stool": (20, 14)}
    w, h = sizes.get(key, (16, 16))
    return [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]


def object_mat(key):
    if key in ("stone", "anvil", "oven", "forge", "kugel"):
        return "stone" if key != "anvil" else "iron"
    if key in ("brick",):
        return "brick"
    if key in ("campfire",):
        return "stone"
    return "plank" if key in ("planks", "platform", "door", "chest", "table", "bed", "workbench", "stool",
                               "sign_board", "barrel", "loom", "trough") else "log"
