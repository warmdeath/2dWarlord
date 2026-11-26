"""Keyboard + mouse -> the player's intents, and the few physical things you do with your hands:
swing at the world (trees, logs, walls, ore), carry and set things down, and shape wood in the field."""
import math

import pygame

from ..settings import TILE
from ..items.items import ITEMS
from ..items import shaping as SH
from ..poly.objects import PhysObject, objects_near

REACH = 92.0
WORLD_TOOLS = ("axt", "spitzhacke", "hammer", "hellebarde", "streitkolben", "dolch", "sichel", "hacke", "fists")


class FieldShaping:
    """Shaping a log where it lies: axe strokes along guide lines, each stroke wobbles with speed."""

    def __init__(self, obj):
        self.obj = obj
        from shapely.geometry import Polygon
        self.wp = SH.Workpiece(Polygon(obj.pts).buffer(0), obj.mat)
        self.target = 0
        self.stroke = []
        self.stroke_t = 0.0
        self.strokes = 0

    @property
    def key(self):
        return SH.FIELD_TARGETS[self.target % len(SH.FIELD_TARGETS)]


class PlayerController:
    def __init__(self, game):
        self.game = game
        self.mouse_world = (0, 0)
        self.place_cd = 0.0
        self.eat_cd = 0.0
        self.swing_cd = 0.0
        self.place_angle = 0.0
        self.shaping = None
        self.pending_hit = None
        self.hint = None
        self.aim_mode = "mouse"
        self.key_aim = -0.15
        self.last_mouse = None
        self.tool_t = 0.0
        self.need_t = 0.0

    # ------------------------------------------------------------------ input
    def handle(self, dt, keys, mouse_buttons, mouse_pos, events):
        g = self.game
        p = g.player
        it = p.intent
        it.clear()
        ox, oy = g.camera.offset()
        z = getattr(g, "zoom", 1.0)
        mx, my = mouse_pos[0] / z, mouse_pos[1] / z
        wx, wy = mx + ox, my + oy
        self.mouse_world = (wx, wy)
        self.place_cd = max(0.0, self.place_cd - dt)
        self.eat_cd = max(0.0, self.eat_cd - dt)
        self.swing_cd = max(0.0, self.swing_cd - dt)
        if p.dead:
            return
        clicked = any(e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 for e in events)
        released = any(e.type == pygame.MOUSEBUTTONUP and e.button == 1 for e in events)
        lmb = mouse_buttons[0] and g.ui.build_sel is None
        shift = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        for e in events:
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_c:
                    self.toggle_shaping()
                elif e.key == pygame.K_r:
                    self.place_angle = (self.place_angle + math.pi / 4) % (math.pi * 2)
                elif e.key == pygame.K_g and getattr(p, "carrying", None) is not None:
                    g.throw(p)
                elif self.shaping is not None and e.key in (pygame.K_q, pygame.K_e, pygame.K_TAB):
                    self.shaping.target += -1 if e.key == pygame.K_q else 1
                    k = self.shaping.key
                    de, en = SH.describe(k)
                    g.ui.toast(f"[{de}|{en}] — follow the dashed lines with the [Axt|axe]", 2.5)
                elif self.shaping is not None and e.key in (pygame.K_RETURN, pygame.K_f):
                    self.finish_shaping()
                elif self.shaping is not None and e.key == pygame.K_ESCAPE:
                    self.cancel_shaping()
        # field shaping takes the hands (and the mouse)
        if self.shaping is not None:
            self.update_shaping(dt, lmb, clicked, released, wx, wy)
            return
        left = keys[pygame.K_a] or keys[pygame.K_LEFT]
        right = keys[pygame.K_d] or keys[pygame.K_RIGHT]
        it.mx = (1 if right else 0) - (1 if left else 0)
        it.run = shift and getattr(p, "carrying", None) is None
        it.crouch = keys[pygame.K_s] or keys[pygame.K_DOWN]
        it.down = it.crouch
        it.up = keys[pygame.K_w] or keys[pygame.K_UP]
        it.jump_held = keys[pygame.K_SPACE] or it.up and p.in_water > 0.3
        it.block = keys[pygame.K_k] or mouse_buttons[2]
        for e in events:
            if e.type == pygame.KEYDOWN and e.key == pygame.K_SPACE:
                it.jump = True
            if e.type == pygame.KEYDOWN and e.key == pygame.K_j:
                it.attack = True
        dx = wx - p.cx
        dy = wy - (p.y + 14)
        self.hint = None
        # the mouse is where your hands and weapon aim; with a weapon drawn (or a tool at work) you face it
        p.aim_pt = (wx, wy)
        wdk = p.weapon_def.kind
        busy_tool = p.action is not None and p.action.get("kind") in ("tool", "attack")
        p.face_to = (1 if dx > 0 else -1) if abs(dx) > 6 and p.mount is None and (
            busy_tool or (wdk == "melee" and p.weapon_drawn and p.weapon_key != "fists")) else 0
        if mouse_pos != self.last_mouse:
            if self.last_mouse is not None:
                self.aim_mode = "mouse"
            self.last_mouse = mouse_pos
        if p.weapon_def.kind in ("bow", "crossbow") and getattr(p, "carrying", None) is None:
            jkey = keys[pygame.K_j]
            if jkey or any(e.type == pygame.KEYDOWN and e.key == pygame.K_j for e in events):
                self.aim_mode = "keys"
            if lmb:
                self.aim_mode = "mouse"
            if self.aim_mode == "keys":
                # keyboard archery: hold J to draw, W/S (or the arrow keys) raise and lower the bow, A/D turn
                up = keys[pygame.K_w] or keys[pygame.K_UP]
                down = keys[pygame.K_s] or keys[pygame.K_DOWN]
                if p.weapon_def.kind == "crossbow":
                    # the crossbow is spanned already: hold J to aim, release to loose the bolt
                    it.attack = any(e.type == pygame.KEYUP and e.key == pygame.K_j for e in events)
                if jkey:
                    rate = 1.1 if not keys[pygame.K_LSHIFT] else 0.35      # Shift: fine aim
                    self.key_aim += ((1 if down else 0) - (1 if up else 0)) * rate * dt
                    self.key_aim = max(-1.45, min(1.2, self.key_aim))
                    if jkey:
                        it.up = it.down = it.crouch = False
                        it.jump_held = False
                        if it.mx:
                            p.facing = 1 if it.mx > 0 else -1
                            it.mx = 0                 # turning, not walking, while the string is drawn
                it.aim = self.key_aim
                it.attack_held = jkey
                self.hint = "J halten: zielen/spannen · W/S: höher/tiefer (Shift fein) · A/D: drehen · loslassen: Schuss"
            else:
                # mouse archery: the bow points where the mouse points, and you turn to face it
                if abs(dx) > 4:
                    p.facing = 1 if dx > 0 else -1
                it.aim = max(-1.45, min(1.2, math.atan2(dy, abs(dx) + 0.001)))
                self.key_aim = it.aim
                it.attack_held = lmb
                self.hint = "Maus: zielen · Linksklick halten: spannen, loslassen: Schuss · or J + W/S"
            if lmb and clicked:
                it.attack = True
        # boat
        if p.boat is not None:
            b = p.boat
            if it.mx:
                b.facing = 1 if it.mx > 0 else -1
            if it.up:
                b.sail_target = min(1.0, b.sail_target + dt * 0.8)
            if it.crouch:
                b.sail_target = max(0.0, b.sail_target - dt * 0.8)
            b.rowing = it.run
            b._wind = g.env.wind
            p.facing = b.facing
            if it.jump:
                g.leave_boat(p, b)
            return
        in_reach = math.hypot(wx - p.cx, wy - p.cy) < REACH
        # carrying something big: set it down where the mouse points (Shift: fix it in place)
        if getattr(p, "carrying", None) is not None:
            it.run = False
            if clicked and in_reach and self.place_cd <= 0:
                g.put_down(p, wx, wy, self.place_angle, anchor=shift)
                self.place_cd = 0.3
            return
        held = p.inv.held()
        hd = ITEMS.get(held) if held else None
        if hd is not None and hd.place in ("object", "station", "seed", "plant") and hd.cat in ("place",):
            if clicked and in_reach and self.place_cd <= 0:
                if g.place_item(p, held, wx, wy, self.place_angle, anchor=shift or hd.place == "station"):
                    self.place_cd = 0.25
                    self.tool_motion(p, "place", wx, wy)
            return
        if hd is not None and hd.cat == "heal" and clicked and self.eat_cd <= 0:
            g.bandage(p)
            self.eat_cd = 0.6
            return
        if hd is not None and hd.cat == "food" and clicked and self.eat_cd <= 0:
            g.eat(p, held)
            self.eat_cd = 0.4
            return
        if clicked and in_reach:
            if p.weapon_key == "hacke" and g.till(wx):
                self.tool_motion(p, "till", wx, g.world.surface_y(wx))
                return
            if held == "mist" and g.manure(wx):
                self.tool_motion(p, "place", wx, g.world.surface_y(wx))
                return
            if p.weapon_key == "sichel" and g.harvest(wx, by=p):
                self.tool_motion(p, "reap", wx, g.world.surface_y(wx) - 6)
                return
        wd = p.weapon_def
        # what is under the mouse, and what would you use on it?
        act = g.world_action(p, wx, wy) if wd.kind not in ("bow", "crossbow") else None
        if act is not None and wd.kind == "melee" and self.enemy_near():
            act = None            # in a fight, a click is a blow, not woodwork
        self.tool_t = max(0.0, self.tool_t - dt)
        if act is not None:
            verb, tools, (hx, hy) = act
            owned = [t_ for t_ in tools if p.inv.count(t_)]
            ok = wd.key in tools
            names = {"fell": "Baum fällen (fell the tree)", "cut": "Stamm zerteilen (cut the trunk)",
                     "mine": "Erz abbauen (mine)", "break": "abreißen (break)", "break_wood": "abreißen (break)",
                     "dig": "graben (dig)"}
            if ok:
                self.hint = f"Linksklick halten: {names[verb]}"
            elif owned:
                self.hint = f"Linksklick: {names[verb]} — mit {ITEMS[owned[0]].de}"
            else:
                self.hint = f"{names[verb]}: you need a {ITEMS[tools[0]].de} ({ITEMS[tools[0]].en})"
            # smart tool: reach for the right tool when you click the world (not in the middle of a fight)
            if lmb and not ok and owned and not self.enemy_near():
                self.equip_tool(owned[0])
                wd = p.weapon_def
                ok = True
            if lmb and self.swing_cd <= 0 and (ok or (clicked and verb == "dig" and wd.key == "fists")):
                p.facing = 1 if hx > p.cx else -1
                style = self.style_for(verb, wd.key)
                # the stroke lands where you point (a tree is struck at the height of the cursor)
                ty = hy if verb != "fell" else max(min(wy, hy + 10), hy - 34)
                dur, hit = self.tool_motion(p, style, hx, ty, wd.speed)
                self.swing_cd = dur * 0.98
                self.pending_hit = [hit, hx, hy]
                g.sfx("swing")
            elif lmb and not ok and clicked and not owned:
                if self.need_t <= 0:
                    self.need_t = 3.0
                    g.ui.toast(f"You need a [{ITEMS[tools[0]].de}|{ITEMS[tools[0]].en}] for that.", 2.5)
            self.need_t = max(0.0, self.need_t - dt)
        if act is None and lmb and wd.kind in ("melee", "tool", "torch") and clicked:
            p.facing = 1 if dx > 0 else -1
            it.attack = True
            if wd.kind == "torch" and in_reach:
                g.try_ignite_tile(int(wx // TILE), int(wy // TILE))
        if self.pending_hit is not None:
            self.pending_hit[0] -= dt
            if self.pending_hit[0] <= 0:
                _, hx, hy = self.pending_hit
                self.pending_hit = None
                dmg = max(8.0, wd.dmg) * (0.5 + 0.5 * p.stamina / max(1, p.max_stamina))
                p.stamina = max(0.0, p.stamina - 4)
                g.hit_world(p, hx, hy, dmg, wd.dtype if hasattr(wd, "dtype") else "cut")

    @staticmethod
    def style_for(verb, key):
        """Which working motion a tool makes on what."""
        if verb == "dig":
            return {"schaufel": "shovel", "hacke": "till", "fists": "place"}.get(key, "pick")
        if verb in ("fell",):
            return "chop"
        if verb == "cut":
            return "buck"
        if verb == "mine":
            return "pick"
        if verb in ("break", "break_wood"):
            return {"axt": "chop", "hellebarde": "chop", "spitzhacke": "pick"}.get(key, "hammer")
        return "hammer"

    def tool_motion(self, p, style, tx, ty, speed=1.0):
        """Start a working motion aimed at (tx, ty); returns (duration, time of the hit)."""
        from ..gfx.rig import TOOL_DUR, TOOL_HIT
        dur = TOOL_DUR.get(style, 0.5) / max(0.6, speed)
        p.facing = 1 if tx > p.cx else -1
        p.action = {"kind": "tool", "style": style, "t": 0.0, "dur": dur, "tx": tx, "ty": ty}
        return dur, dur * TOOL_HIT.get(style, 0.5)

    @staticmethod
    def suits(key, verb):
        return {"fell": key in ("axt", "hellebarde"), "cut": key in ("axt", "hellebarde"),
                "mine": key == "spitzhacke", "dig": key in ("schaufel", "spitzhacke", "hacke"),
                "break": key in ("hammer", "spitzhacke", "axt", "streitkolben")}.get(verb, False)

    def enemy_near(self):
        g = self.game
        p = g.player
        return any(not h.dead and h is not p and g.hostile(p, h) and abs(h.cx - p.cx) < 260
                   for h in g.humanoids) or any(not a.dead and a.behaviour in ("predator", "aggressive") and
                                                abs(a.cx - p.cx) < 200 for a in g.animals)

    def equip_tool(self, key):
        g = self.game
        inv = g.player.inv
        if key in inv.belt:
            inv.selected = inv.belt.index(key)
        else:
            # take a free belt hook, or swap out whatever is not a weapon
            slot = inv.belt.index(None) if None in inv.belt else next(
                (i for i, k in enumerate(inv.belt) if k and ITEMS[k].cat not in ("weapon",)), inv.selected)
            inv.belt[slot] = key
            inv.selected = slot
        g.sync_held()
        g.fx.text(g.player.cx, g.player.y - 18, ITEMS[key].de, (240, 220, 170), gloss=ITEMS[key].en, life=0.8)

    def world_target(self, x, y):
        """Is there something of the world under the mouse to swing at?"""
        g = self.game
        w = g.world
        for t in w.near("tree_chunks", x - 60, x + 60):
            if t.state == "stand" and abs(t.x - x) < t.tw / 2 + 10 and t.y - t.h * 0.6 < y < t.y + 4:
                return True
        for o in objects_near(w, x, y, 6):
            if o.shape is not None and o.shape.point_query((x, y)).distance < 4:
                return True
        for ore in w.ores:
            if ore["left"] > 0 and abs(ore["x"] - x) < 14 and abs(ore["y"] - y) < 14:
                return True
        from ..poly.prefab import piece_at
        pc = piece_at(w, x, y)
        return pc is not None and pc.solid

    # ------------------------------------------------------------------ field shaping
    def toggle_shaping(self):
        g = self.game
        p = g.player
        if self.shaping is not None:
            self.finish_shaping()
            return
        if getattr(p, "carrying", None) is not None:
            g.put_down(p)
        best, bd = None, 70
        for o in g.world.objects:
            if o.kind in ("log", "crafted", "piece") and o.mat in ("log", "plank", "timber") and not o.anchored and \
                    o.crown is None:
                d = math.hypot(o.x - p.cx, o.y - p.cy)
                if d < bd:
                    best, bd = o, d
        if best is None:
            g.ui.toast("Put a [Stamm|log] on the ground first, then press C to shape it. (At a [Werkbank|workbench] "
                       "you can work precisely.)", 4)
            return
        if p.weapon_key not in ("axt", "dolch", "schwert", "langschwert", "hellebarde"):
            for k in ("axt", "dolch"):
                if p.inv.count(k):
                    p.inv.to_belt(k)
                    p.inv.selected = p.inv.belt.index(k)
                    g.sync_held()
                    break
            else:
                g.ui.toast("You need an [Axt|axe] or a [Dolch|knife] to shape wood.", 3)
                return
        best.detach()
        best.anchored = True
        best.attach(g.world)
        self.shaping = FieldShaping(best)
        de, en = SH.describe(self.shaping.key)
        g.ui.toast(f"[Schnitzen|shaping]: make a [{de}|{en}]. Drag along the dashed lines. Q/E: other shape, "
                   f"Enter: done, Esc: stop.", 6)

    def to_local(self, x, y):
        o = self.shaping.obj
        b = o.body
        lx, ly = b.world_to_local((x, y))
        return (lx, ly)

    def update_shaping(self, dt, lmb, clicked, released, wx, wy):
        g = self.game
        p = g.player
        s = self.shaping
        o = s.obj
        if o.removed or math.hypot(o.x - p.cx, o.y - p.cy) > 140:
            self.cancel_shaping()
            return
        p.facing = 1 if wx > p.cx else -1
        if clicked:
            s.stroke = [(wx, wy)]
            s.stroke_t = 0.0
        elif lmb and s.stroke:
            s.stroke_t += dt
            if math.hypot(wx - s.stroke[-1][0], wy - s.stroke[-1][1]) > 3:
                s.stroke.append((wx, wy))
        if released and len(s.stroke) >= 2:
            a, b = s.stroke[0], s.stroke[-1]
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            if L > 8:
                speed = L / max(0.05, s.stroke_t)
                skill = 0.55 + min(0.4, p.stats.get("shaped", 0) * 0.02) if hasattr(p, "stats") else 0.6
                if p.weapon_key == "dolch":
                    skill += 0.1
                a2, b2 = SH.wobble(a, b, speed, skill, g.rng)
                la, lb = self.to_local(*a2), self.to_local(*b2)
                if s.wp.saw(la, lb):
                    s.strokes += 1
                    p.action = {"kind": "use", "t": 0.0, "dur": 0.35}
                    p.stamina = max(0.0, p.stamina - 6)
                    g.fx.debris(wx, wy, (196, 160, 108), 4)
                    g.sfx("chop")
                    self.apply_shape()
            s.stroke = []

    def apply_shape(self):
        """Show the work on the real object right away."""
        g = self.game
        s = self.shaping
        o = s.obj
        pts = s.wp.points()
        if len(pts) < 3:
            return
        from ..poly.objects import centroid
        cx, cy = centroid(pts)
        c, sn = math.cos(o.body.angle), math.sin(o.body.angle)
        wx, wy = o.body.local_to_world((cx, cy))
        new = [(x - cx, y - cy) for x, y in pts]
        o.detach()
        o.pts = new
        o.pos = (wx, wy)
        o.radius = max(math.hypot(x, y) for x, y in new)
        o.attach(g.world)
        s.wp = SH.Workpiece(__import__("shapely.geometry", fromlist=["Polygon"]).Polygon(new).buffer(0), o.mat)
        for off in s.wp.offcuts:
            pass

    def finish_shaping(self):
        g = self.game
        s = self.shaping
        if s is None:
            return
        self.shaping = None
        o = s.obj
        key, q, ranking = SH.identify(s.wp.poly, lab=False)
        o.detach()
        o.anchored = False
        if key is not None:
            item, de, en = SH.TEMPLATES[key][0], SH.TEMPLATES[key][1], SH.TEMPLATES[key][2]
            o.kind = "crafted"
            o.item = item
            o.shape_key = item
            o.quality = q
            o.mat = "plank" if key in ("planks", "door", "sign_board") else o.mat
            g.ui.toast(f"[{de}|{en}] — [Güte|quality] {int(q * 100)}%. E to pick up or carry it.", 4)
            g.player.stats["shaped"] = g.player.stats.get("shaped", 0) + 1
            g.emit("shaped", key=item, q=q)
        elif s.strokes:
            o.kind = "crafted"
            o.item = "wood"
            o.shape_key = None
            o.name = "Rohling"
            g.ui.toast("A [Rohling|rough blank]: it is no known shape, but you can still place it.", 3)
        o.attach(g.world)

    def cancel_shaping(self):
        s = self.shaping
        self.shaping = None
        if s is not None and not s.obj.removed:
            s.obj.detach()
            s.obj.anchored = False
            s.obj.attach(self.game.world)

    # ------------------------------------------------------------------ drawing (placement preview, guides)
    def draw_trajectory(self, surf, ox, oy):
        """Where the arrow will fly, as a dotted arc (gravity, wind and draw strength included)."""
        g = self.game
        p = g.player
        wd = p.weapon_def
        act = p.action
        if wd.kind == "bow":
            if act is None or act.get("kind") != "bow":
                return
            draw = act.get("draw", 0.0)
            speed, grav, wk = 320 + 600 * draw, 520.0, 70.0
        elif wd.kind == "crossbow":
            if self.aim_mode == "keys" and not pygame.key.get_pressed()[pygame.K_j]:
                return
            speed, grav, wk = 950.0, 300.0, 30.0
            draw = 1.0
        else:
            return
        if g.env.is_raining() and wd.kind == "bow":
            speed *= 0.85
        aim = act.get("aim", p.intent.aim) if act else p.intent.aim
        f = p.facing
        x, y = p.cx + f * 10, p.y + 14
        vx, vy = math.cos(aim) * speed * f, math.sin(aim) * speed
        w = g.world
        dt = 1 / 30
        a = 90 + int(120 * draw)
        for i in range(45):
            vy += grav * dt
            vx += g.env.wind * wk * dt
            x += vx * dt
            y += vy * dt
            if w.solid_point(x, y):
                pygame.draw.circle(surf, (255, 220, 150), (int(x - ox), int(y - oy)), 4, 1)
                break
            if i % 2 == 0:
                pygame.draw.circle(surf, (255, 240, 200) if i < 30 else (200, 190, 170), (int(x - ox), int(y - oy)),
                                   2 if i < 20 else 1)

    def draw_world(self, surf, ox, oy):
        g = self.game
        p = g.player
        wx, wy = self.mouse_world
        self.draw_trajectory(surf, ox, oy)
        if self.shaping is not None:
            s = self.shaping
            o = s.obj
            if o.body is None:
                return
            cuts, guide = s.wp.guide_cuts(s.key)
            t = g.env.time
            for a, b in cuts:
                A = o.body.local_to_world(a)
                B = o.body.local_to_world(b)
                L = math.hypot(B[0] - A[0], B[1] - A[1])
                n = max(1, int(L // 6))
                for i in range(0, n, 2):
                    f0, f1 = i / n, min(1.0, (i + 1) / n)
                    pygame.draw.line(surf, (255, 236, 150), (A[0] + (B[0] - A[0]) * f0 - ox, A[1] + (B[1] - A[1]) * f0 - oy),
                                     (A[0] + (B[0] - A[0]) * f1 - ox, A[1] + (B[1] - A[1]) * f1 - oy), 2)
            gp = [o.body.local_to_world(c) for c in list(guide.exterior.coords)]
            pygame.draw.lines(surf, (255, 255, 255), True, [(x - ox, y - oy) for x, y in gp], 1)
            if len(s.stroke) >= 2:
                pygame.draw.lines(surf, (255, 120, 80), False, [(x - ox, y - oy) for x, y in s.stroke], 2)
            de, en = SH.describe(s.key)
            key, q, _ = SH.identify(s.wp.poly, lab=False)
            from ..ui.common import text
            label = f"{de} ({en})" + (f"  — erkannt: {SH.TEMPLATES[key][1]} {int(q * 100)}%" if key else "")
            text(surf, label, (o.x - ox, o.y - oy - 46), 13, (255, 240, 200), center=True)
            return
        carrying = getattr(p, "carrying", None)
        held = p.inv.held()
        hd = ITEMS.get(held) if held else None
        if carrying is None and not (hd is not None and hd.place in ("object", "station") and hd.cat == "place"):
            return
        if math.hypot(wx - p.cx, wy - p.cy) > REACH:
            return
        if carrying is not None:
            pts = carrying.pts
        else:
            from .world_ops import object_shape
            pts = object_shape(held)
        c, s_ = math.cos(self.place_angle), math.sin(self.place_angle)
        sp = [(wx + x * c - y * s_ - ox, wy + x * s_ + y * c - oy) for x, y in pts]
        ghost = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        pygame.draw.polygon(ghost, (255, 240, 200, 70), sp)
        pygame.draw.polygon(ghost, (255, 240, 200, 180), sp, 1)
        surf.blit(ghost, (0, 0))
