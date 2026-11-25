"""Animals: livestock, wildlife and the horse (rideable mount)."""
import math
import random

import pygame

from ..settings import TILE, HORSE_WALK, HORSE_GALLOP, JUMP_SPEED
from .body import Body

SPECIES = {
    #          de        en        w   h   hp  speed  behaviour    drops                     colour
    "horse": ("Pferd", "horse", 40, 30, 120, 90, "herd", {"meat": 4, "leather": 3}, (120, 82, 52)),
    "cow": ("Kuh", "cow", 34, 24, 80, 40, "herd", {"meat": 5, "leather": 2}, (220, 214, 200)),
    "sheep": ("Schaf", "sheep", 22, 16, 40, 45, "herd", {"meat": 2, "wool": 3}, (236, 232, 220)),
    "pig": ("Schwein", "pig", 24, 16, 50, 50, "herd", {"meat": 4}, (226, 160, 150)),
    "chicken": ("Huhn", "chicken", 10, 10, 10, 60, "herd", {"meat": 1}, (240, 236, 226)),
    "deer": ("Hirsch", "deer", 30, 26, 60, 150, "shy", {"meat": 4, "leather": 2}, (150, 100, 60)),
    "boar": ("Wildschwein", "wild boar", 26, 18, 80, 120, "aggressive", {"meat": 5, "leather": 1}, (80, 64, 50)),
    "wolf": ("Wolf", "wolf", 26, 16, 60, 165, "predator", {"leather": 2}, (110, 110, 116)),
    "bear": ("Bär", "bear", 38, 28, 220, 110, "aggressive", {"meat": 8, "leather": 5}, (90, 64, 44)),
    "fish": ("Fisch", "fish", 14, 8, 6, 70, "fish", {"fish": 1}, (150, 170, 190)),
}


class Animal(Body):
    kind = "animal"
    step_up = 1

    def __init__(self, x, y, species, faction=None):
        sp = SPECIES[species]
        self.w, self.h = sp[2], sp[3]
        super().__init__(x, y)
        self.species = species
        self.de, self.en = sp[0], sp[1]
        self.max_hp = self.hp = float(sp[4])
        self.base_speed = sp[5]
        self.behaviour = sp[6]
        self.drops = sp[7]
        self.color = sp[8]
        self.faction = faction or ("wild" if self.behaviour in ("predator", "aggressive") else "beast")
        self.dead = False
        self.dead_t = 0.0
        self.wander_t = random.uniform(1, 4)
        self.target_vx = 0.0
        self.walk_phase = random.uniform(0, 6)
        self.hurt_flash = 0.0
        self.flee_t = 0.0
        self.attack_cd = 0.0
        self.anim_t = random.uniform(0, 10)
        self.home_x = x
        self.owner = None
        self.rider = None
        self.weight = 0.9
        self.formation = None
        self.mount = None
        self.blocking = False
        self.stagger = 0.0
        self.tethered = False
        if species == "fish":
            self.weight = 0.0
        self.burning = 0.0

    def take_hit(self, game, attacker, dmg, dtype, posture, flags=(), high=True, source_x=None, arrow=False,
                 **kw):
        if self.dead:
            return "immune"
        self.hp -= dmg
        self.hurt_flash = 0.15
        sx = source_x if source_x is not None else (attacker.cx if attacker else self.cx)
        d = 1 if self.cx >= sx else -1
        self.vx += d * (80 + dmg * 3)
        self.flee_t = 6.0
        game.fx.blood(self.cx, self.cy, 6, d)
        game.fx.number(self.cx, self.y - 4, int(dmg))
        if self.behaviour in ("aggressive", "predator") and attacker is not None:
            self.enemy = attacker
        if self.hp <= 0:
            self.dead = True
            if self.rider is not None:
                game.dismount(self.rider, thrown=True)
            game.on_animal_death(self, attacker)
        return "hit"

    def update(self, game, dt):
        self.anim_t += dt
        self.hurt_flash = max(0.0, self.hurt_flash - dt)
        self.attack_cd = max(0.0, self.attack_cd - dt)
        if self.dead:
            self.dead_t += dt
            self.vx *= 0.9
            self.physics(game.world, dt)
            return
        if self.rider is not None:
            return   # the rider's update drives the horse (ride_control); don't integrate twice
        if self.species == "fish":
            self._fish(game, dt)
            return
        pl = game.player
        self.flee_t = max(0.0, self.flee_t - dt)
        target = 0.0
        enemy = getattr(self, "enemy", None)
        if self.behaviour == "predator" and (enemy is None or enemy.dead):
            enemy = None
            best = 260
            for h in game.humanoids:
                if h.dead:
                    continue
                d = abs(h.cx - self.cx)
                if d < best and abs(h.cy - self.cy) < 80 and (game.env.is_night() or self.species == "wolf"):
                    best, enemy = d, h
            self.enemy = enemy
        if enemy is not None and not enemy.dead and abs(enemy.cx - self.cx) < 500 and self.hp > self.max_hp * 0.25:
            d = enemy.cx - self.cx
            self.facing = 1 if d > 0 else -1
            target = self.facing * self.base_speed
            if abs(d) < self.w * 0.5 + 16 and abs(enemy.cy - self.cy) < 40 and self.attack_cd <= 0:
                self.attack_cd = 1.1
                dmg = {"wolf": 9, "bear": 24, "boar": 14}.get(self.species, 6)
                enemy.take_hit(game, self, dmg, "cut", 12, high=False, pen=3)
                if self.on_ground:
                    self.vy = -200
        elif self.flee_t > 0 and pl is not None:
            self.facing = 1 if self.cx > pl.cx else -1
            target = self.facing * self.base_speed * 1.4
        else:
            if self.behaviour == "shy" and pl is not None and abs(pl.cx - self.cx) < 120 and \
                    pl.state not in ("crouch",):
                self.flee_t = 3.0
            self.wander_t -= dt
            if self.wander_t <= 0:
                self.wander_t = random.uniform(2, 6)
                r = random.random()
                if self.tethered:
                    self.target_vx = 0
                elif r < 0.45:
                    self.target_vx = 0.0
                else:
                    self.target_vx = random.choice((-1, 1)) * self.base_speed * 0.3
                    if abs(self.cx - self.home_x) > 300:
                        self.target_vx = math.copysign(self.base_speed * 0.3, self.home_x - self.cx)
            target = self.target_vx
            if target:
                self.facing = 1 if target > 0 else -1
        self.vx += (target - self.vx) * min(1.0, dt * 4)
        if self.blocked and self.on_ground and abs(target) > 1:
            self.vy = -JUMP_SPEED * 0.75
        if self.in_water > 0.4:
            self.vy -= 900 * dt
        self.physics(game.world, dt)
        self.walk_phase += abs(self.vx) * dt * 0.09

    def _fish(self, game, dt):
        w = game.world
        tx, ty = int(self.cx // TILE), int(self.cy // TILE)
        in_w = w.inside(tx, ty) and w.liq[tx, ty] > 4
        self.wander_t -= dt
        if self.wander_t <= 0:
            self.wander_t = random.uniform(1, 3)
            self.vx = random.uniform(-1, 1) * self.base_speed
            self.vy = random.uniform(-0.4, 0.4) * self.base_speed
        if not in_w:
            self.vy += 900 * dt
            if self.on_ground:
                self.hp -= dt * 2
                self.vy = -120
                if self.hp <= 0:
                    self.dead = True
        nx, ny = self.x + self.vx * dt, self.y + self.vy * dt
        ntx, nty = int((nx + self.w / 2) // TILE), int((ny + self.h / 2) // TILE)
        if w.inside(ntx, nty) and w.liq[ntx, nty] > 4 and not w.solid(ntx, nty) or not in_w:
            self.x, self.y = nx, ny
            if not in_w:
                self.physics(w, dt)
        else:
            self.vx, self.vy = -self.vx, -self.vy
        if self.vx:
            self.facing = 1 if self.vx > 0 else -1

    # ------------------------------------------------------------- mount control
    def ride_control(self, game, rider, it, dt):
        if self.species != "horse":
            return
        speed = HORSE_GALLOP if it.run else HORSE_WALK
        target = it.mx * speed
        self.vx += (target - self.vx) * min(1.0, dt * (2.0 if it.run else 3.0))
        if it.mx:
            self.facing = 1 if it.mx > 0 else -1
        if it.jump and self.on_ground:
            self.vy = -JUMP_SPEED * 1.05
        if self.in_water > 0.4:
            self.vy -= 1000 * dt
            self.vx *= 0.97
        self.step_up = 2
        self.physics(game.world, dt)
        self.walk_phase += abs(self.vx) * dt * 0.05
        if self.void_fall > 0:
            rider.void_fall = self.void_fall

    # ------------------------------------------------------------- drawing
    def draw(self, surf, ox, oy):
        x, y = self.x - ox, self.y - oy + self.step_smooth
        if not (-80 < x < surf.get_width() + 80 and -80 < y < surf.get_height() + 80):
            return
        if self.species == "horse":
            draw_horse(surf, self.cx - ox, self.feet - oy + self.step_smooth, self.facing, self.walk_phase,
                       self.color, abs(self.vx) > 4, dead=self.dead, gallop=abs(self.vx) > HORSE_WALK * 1.2,
                       saddle=self.owner is not None or self.rider is not None)
            return
        f = self.facing
        c = self.color if not self.hurt_flash else (255, 255, 255)
        cx, fy = self.cx - ox, self.feet - oy + self.step_smooth
        if self.dead:
            pygame.draw.ellipse(surf, c, (cx - self.w / 2, fy - self.h * 0.5, self.w, self.h * 0.5))
            return
        if self.species == "fish":
            pygame.draw.ellipse(surf, c, (cx - 7, fy - 8, 14, 7))
            pygame.draw.polygon(surf, c, [(cx - f * 7, fy - 5), (cx - f * 12, fy - 9), (cx - f * 12, fy - 1)])
            return
        if self.species == "chicken":
            bob = math.sin(self.walk_phase * 3) * 1
            pygame.draw.ellipse(surf, c, (cx - 5, fy - 9 + bob, 10, 7))
            pygame.draw.circle(surf, c, (cx + f * 4, fy - 10 + bob), 3)
            pygame.draw.polygon(surf, (230, 160, 40), [(cx + f * 6, fy - 10), (cx + f * 9, fy - 9), (cx + f * 6, fy - 8)])
            pygame.draw.circle(surf, (200, 40, 40), (cx + f * 4, fy - 13 + bob), 1)
            pygame.draw.line(surf, (230, 160, 40), (cx, fy - 3), (cx, fy), 1)
            return
        w, h = self.w, self.h
        body_h = h * 0.55
        leg_h = h * 0.4
        by = fy - leg_h - body_h
        ph = self.walk_phase
        legc = tuple(int(v * 0.7) for v in c)
        for i, lx in enumerate((-w * 0.32, -w * 0.2, w * 0.22, w * 0.34)):
            sw = math.sin(ph + (i % 2) * math.pi) * 0.5 if abs(self.vx) > 4 else 0
            x0 = cx + lx * f
            pygame.draw.line(surf, legc, (x0, fy - leg_h), (x0 + sw * leg_h * f, fy), 3)
        pygame.draw.ellipse(surf, c, (cx - w / 2, by, w, body_h + 2))
        hx = cx + f * w * 0.48
        hy = by + body_h * 0.2
        head_r = {"cow": 6, "sheep": 5, "pig": 6, "deer": 5, "boar": 6, "wolf": 5, "bear": 8}.get(self.species, 5)
        pygame.draw.circle(surf, c, (hx, hy), head_r)
        pygame.draw.circle(surf, (20, 20, 20), (hx + f * head_r * 0.4, hy - 1), 1)
        if self.species == "sheep":
            for k in range(5):
                pygame.draw.circle(surf, (250, 248, 240), (cx - w * 0.35 + k * w * 0.17, by + 3), 4)
            pygame.draw.circle(surf, (60, 56, 50), (hx, hy), 4)
        elif self.species == "cow":
            pygame.draw.circle(surf, (60, 50, 44), (cx - f * 4, by + 6), 4)
            pygame.draw.line(surf, (230, 220, 200), (hx - 4, hy - 5), (hx - 7, hy - 9), 2)
            pygame.draw.line(surf, (230, 220, 200), (hx + 4, hy - 5), (hx + 7, hy - 9), 2)
        elif self.species == "pig":
            pygame.draw.ellipse(surf, (240, 170, 170), (hx + f * 3 - 3, hy - 1, 6, 5))
        elif self.species == "deer":
            for s in (-1, 1):
                pygame.draw.line(surf, (200, 180, 140), (hx, hy - 4), (hx + s * 5, hy - 14), 2)
                pygame.draw.line(surf, (200, 180, 140), (hx + s * 3, hy - 9), (hx + s * 8, hy - 11), 1)
        elif self.species in ("wolf",):
            pygame.draw.polygon(surf, c, [(hx, hy - 4), (hx + f * 2, hy - 10), (hx + f * 4, hy - 3)])
            pygame.draw.polygon(surf, c, [(hx + f * 3, hy), (hx + f * 11, hy + 2), (hx + f * 3, hy + 4)])
            pygame.draw.line(surf, c, (cx - f * w / 2, by + 4), (cx - f * (w / 2 + 8), by + 8), 3)
        elif self.species == "boar":
            pygame.draw.line(surf, (240, 236, 226), (hx + f * 4, hy + 2), (hx + f * 6, hy - 3), 2)
        if self.hurt_flash:
            pygame.draw.ellipse(surf, (255, 255, 255), (cx - w / 2, by, w, body_h + 2), 1)


def draw_horse(surf, cx, fy, f, ph, color, moving, dead=False, gallop=False, saddle=False, shade=1.0):
    c = tuple(int(v * shade) for v in color)
    dark = tuple(int(v * 0.6) for v in c)
    if dead:
        pygame.draw.ellipse(surf, c, (cx - 22, fy - 14, 44, 14))
        return
    leg = 15
    by = fy - leg - 14
    amp = 0.7 if gallop else 0.4
    for i, lx in enumerate((-15, -10, 11, 16)):
        a = math.sin(ph * (1.6 if gallop else 1.0) + (i % 2) * math.pi + (i // 2) * 0.6) * amp if moving else 0
        x0 = cx + lx * f
        kx = x0 + math.sin(a) * leg * 0.5 * f
        ky = fy - leg * 0.5
        pygame.draw.line(surf, dark, (x0, fy - leg), (kx, ky), 3)
        pygame.draw.line(surf, dark, (kx, ky), (kx + math.sin(a * 1.4) * 3 * f, fy), 3)
    bob = math.sin(ph * 2) * (2 if gallop else 1) if moving else 0
    pygame.draw.ellipse(surf, c, (cx - 21, by + bob, 42, 16))
    nx = cx + f * 16
    pygame.draw.polygon(surf, c, [(nx - f * 4, by + 4 + bob), (nx + f * 6, by - 14 + bob), (nx + f * 11, by - 10 + bob),
                                  (nx + f * 4, by + 8 + bob)])
    pygame.draw.ellipse(surf, c, (nx + f * 6 - 6 + (f < 0) * -4, by - 17 + bob, 14, 8))
    pygame.draw.circle(surf, (20, 20, 20), (int(nx + f * 9), int(by - 14 + bob)), 1)
    pygame.draw.line(surf, (40, 30, 24), (nx - f * 1, by + 2 + bob), (nx + f * 5, by - 14 + bob), 3)
    tail_sw = math.sin(ph * 2) * 3
    pygame.draw.line(surf, (40, 30, 24), (cx - f * 20, by + 4 + bob), (cx - f * 26, by + 16 + tail_sw), 3)
    if saddle:
        pygame.draw.rect(surf, (110, 40, 30), (cx - 8, by - 1 + bob, 16, 7), border_radius=2)


def draw_horse_simple(surf, x, y, f, frame, shade, moving):
    draw_horse(surf, x, y, f, frame / 8.0 * math.tau, (120, 82, 52), moving, gallop=moving, saddle=True,
               shade=shade)
