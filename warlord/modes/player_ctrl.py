"""Keyboard + mouse -> player intents, mining, placing and interaction."""
import math

import pygame

from ..settings import TILE
from ..world import tiles as T
from ..items.items import ITEMS
from ..combat.weapons import WEAPONS

REACH_TILES = 5.5


class PlayerController:
    def __init__(self, game):
        self.game = game
        self.mine_target = None
        self.mouse_world = (0, 0)
        self.place_cd = 0.0
        self.eat_cd = 0.0

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
        if p.dead:
            return
        left = keys[pygame.K_a] or keys[pygame.K_LEFT]
        right = keys[pygame.K_d] or keys[pygame.K_RIGHT]
        it.mx = (1 if right else 0) - (1 if left else 0)
        it.run = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        it.crouch = keys[pygame.K_s] or keys[pygame.K_DOWN]
        it.down = it.crouch
        it.up = keys[pygame.K_w] or keys[pygame.K_UP]
        it.jump_held = keys[pygame.K_SPACE] or it.up and p.in_water > 0.3
        it.block = keys[pygame.K_k] or mouse_buttons[2]
        lmb = mouse_buttons[0] and g.ui.build_sel is None
        for e in events:
            if e.type == pygame.KEYDOWN and e.key == pygame.K_SPACE:
                it.jump = True
            if e.type == pygame.KEYDOWN and e.key == pygame.K_j:
                it.attack = True
        # walking into a door opens it (gates open for friends)
        if it.mx and p.mount is None:
            fx = int((p.cx + it.mx * (p.w / 2 + 3)) // TILE)
            for ty in (int((p.feet - 8) // TILE), int((p.feet - 24) // TILE)):
                if g.world.inside(fx, ty):
                    t = g.world.fg[fx, ty]
                    if t == T.DOOR.id:
                        g.open_door(fx, ty)
                    elif t == T.GATE.id and g.can_open_gate(p, fx, ty):
                        g.open_gate(fx, ty)
        elif it.mx and p.mount is not None:
            fx = int((p.mount.cx + it.mx * (p.mount.w / 2 + 3)) // TILE)
            for ty in (int((p.mount.feet - 8) // TILE), int((p.mount.feet - 24) // TILE)):
                if g.world.inside(fx, ty):
                    t = g.world.fg[fx, ty]
                    if t == T.DOOR.id:
                        g.open_door(fx, ty)
                    elif t == T.GATE.id and g.can_open_gate(p, fx, ty):
                        g.open_gate(fx, ty)
        # aim (bow / crossbow): angle from the hand to the mouse
        dx = wx - p.cx
        dy = wy - (p.y + 14)
        if p.weapon_def.kind in ("bow", "crossbow"):
            if (lmb or it.attack) and dx != 0:
                p.facing = 1 if dx > 0 else -1
            it.aim = max(-1.4, min(1.1, math.atan2(dy, abs(dx) + 0.001)))
            it.attack_held = lmb or keys[pygame.K_j]
            if lmb and any(e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 for e in events):
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
        held = p.inv.held()
        hd = ITEMS.get(held) if held else None
        # click logic
        clicked = any(e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 for e in events)
        tx, ty = int(wx // TILE), int(wy // TILE)
        in_reach = math.hypot(wx - p.cx, wy - p.cy) < REACH_TILES * TILE
        if lmb and hd is not None and hd.cat in ("place",) and in_reach:
            if self.place_cd <= 0 and g.try_place(p, held, tx, ty):
                self.place_cd = 0.12
            return
        if hd is not None and hd.cat == "heal" and clicked and self.eat_cd <= 0:
            g.bandage(p)
            self.eat_cd = 0.6
            return
        if hd is not None and hd.cat == "food" and clicked and self.eat_cd <= 0:
            g.eat(p, held)
            self.eat_cd = 0.4
            return
        wd = p.weapon_def
        tool_like = wd.kind == "tool" or (wd.key == "axt" and in_reach and g.world.inside(tx, ty) and
                                          g.world.fg[tx, ty] in (T.LOG.id, T.LEAVES.id, T.PINE.id))
        if lmb and tool_like and in_reach and g.world.inside(tx, ty) and g.world.fg[tx, ty] != 0:
            self.mine(dt, tx, ty)
            return
        if (lmb and wd.kind in ("melee", "tool", "torch")) and (clicked or not tool_like):
            if clicked:
                p.facing = 1 if dx > 0 else -1
                it.attack = True
                if wd.kind == "torch" and in_reach and g.world.inside(tx, ty):
                    g.try_ignite_tile(tx, ty)
        elif lmb and wd.key == "fists" and in_reach and g.world.inside(tx, ty) and g.world.fg[tx, ty] != 0 and \
                T.TILES[g.world.fg[tx, ty]].hardness <= 0.6:
            self.mine(dt, tx, ty, power=0.5)
        if not lmb:
            self.mine_target = None

    def mine(self, dt, tx, ty, power=None):
        g = self.game
        p = g.player
        w = g.world
        tid = int(w.fg[tx, ty])
        td = T.TILES[tid]
        if td.hardness >= 999:
            return
        wd = p.weapon_def
        if power is None:
            power = wd.tool_power.get(td.tool, 0.6) if wd.tool_power else 0.6
            if td.deco:
                power = max(power, 2.0)
        self.mine_target = (tx, ty)
        p.facing = 1 if tx * TILE + 8 > p.cx else -1
        if p.action is None:
            p.action = {"kind": "use", "t": 0.0, "dur": 0.35 / max(0.5, wd.speed)}
            g.sfx("dig")
        if g.damage_tile(tx, ty, power * dt, p):
            self.mine_target = None
