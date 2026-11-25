"""Animals: livestock, wildlife and the horse (rideable mount)."""
import math
import random

import pygame

from ..settings import TILE, HORSE_WALK, HORSE_GALLOP, JUMP_SPEED
from .body import Body
from ..gfx.quadruped import draw_quadruped, draw_horse_at, SPEC
from ..gfx import paint

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
        self.walk_phase += abs(self.vx) * dt / stride_len(self.species, abs(self.vx))
        # grazing: idle herd animals lower their heads now and then
        if self.behaviour in ("herd", "shy") and abs(self.vx) < 3:
            self.graze_t = getattr(self, "graze_t", random.uniform(2, 6)) - dt
            if self.graze_t <= 0:
                self.graze_t = random.uniform(3, 8)
                self.graze_on = not getattr(self, "graze_on", False)
        else:
            self.graze_on = False
        self.graze = getattr(self, "graze", 0.0) + ((1.0 if getattr(self, "graze_on", False) else 0.0) -
                                                    getattr(self, "graze", 0.0)) * min(1.0, dt * 3)

    def _fish(self, game, dt):
        w = game.world
        lvl = w.water_level(self.cx)
        in_w = lvl is not None and lvl + 4 < self.cy < w.surface_y(self.cx) - 2
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
        nl = w.water_level(nx + self.w / 2)
        if (nl is not None and nl + 4 < ny + self.h / 2 < w.surface_y(nx + self.w / 2) - 2) or not in_w:
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
        self.walk_phase += abs(self.vx) * dt / stride_len(self.species, abs(self.vx))
        self.graze = 0.0
        if self.void_fall > 0:
            rider.void_fall = self.void_fall

    # ------------------------------------------------------------- drawing
    def draw(self, surf, ox, oy):
        x, y = self.x - ox, self.y - oy
        if not (-80 < x < surf.get_width() + 80 and -80 < y < surf.get_height() + 80):
            return
        cx, fy = self.cx - ox, self.feet - oy
        if draw_quadruped(surf, self, cx, fy):
            return
        f = self.facing
        c = self.color if not self.hurt_flash else (255, 255, 255)
        if self.species == "fish":
            sw = math.sin(self.anim_t * 8) * 2
            body = [(cx + f * 8, fy - 5), (cx + f * 3, fy - 8.5), (cx - f * 4, fy - 7.5), (cx - f * 7, fy - 5 + sw * 0.3),
                    (cx - f * 4, fy - 2.5), (cx + f * 3, fy - 1.5)]
            pygame.draw.polygon(surf, paint.warm(c, -0.25), [(cx - f * 6, fy - 5), (cx - f * 12, fy - 9 + sw),
                                                             (cx - f * 11, fy - 5), (cx - f * 12, fy - 1 + sw)])
            pygame.draw.polygon(surf, c, body)
            pygame.draw.polygon(surf, paint.warm(c, -0.2), [body[3], body[4], body[5], (cx + f * 8, fy - 5)])
            pygame.draw.line(surf, paint.warm(c, 0.4), (cx + f * 5, fy - 6.5), (cx - f * 4, fy - 6.5), 1)
            pygame.draw.polygon(surf, paint.shade(c, 0.5), body, 1)
            pygame.draw.circle(surf, (20, 20, 20), (cx + f * 5, fy - 5.5), 1.1)
            return
        if self.species == "chicken":
            ph = self.walk_phase * math.tau
            bob = abs(math.sin(ph)) * 1.2 if abs(self.vx) > 3 else 0
            peck = getattr(self, "graze", 0.0)
            for k in (0, 1):
                a_ = math.sin(ph + k * math.pi) * 0.5 if abs(self.vx) > 3 else 0
                pygame.draw.line(surf, (226, 160, 50), (cx - f * 1, fy - 4), (cx - f * 1 + math.sin(a_) * 3, fy), 1)
            by = fy - 7.5 + bob
            # tail feathers, a round body, a folded wing
            for k, ang in enumerate((-2.2, -1.9, -1.6)):
                paint.leaf(surf, paint.shade(c, 0.8 + 0.08 * k), cx - f * 4, by - 1, 6, ang if f > 0 else math.pi - ang, 0.3)
            pygame.draw.ellipse(surf, paint.shade(c, 0.55), (cx - 6, by - 4.5, 12, 9))
            pygame.draw.ellipse(surf, c, (cx - 5.5, by - 4, 11, 8))
            pygame.draw.ellipse(surf, paint.warm(c, -0.15), (cx - 4 - f * 1, by - 1.5, 7, 4.5))
            pygame.draw.ellipse(surf, paint.warm(c, 0.25), (cx - 3.5, by - 3.6, 5, 2.4))
            hx, hy = cx + f * (5 + peck * 2), fy - 12 + bob + peck * 7
            pygame.draw.line(surf, c, (cx + f * 3, by - 2), (hx, hy), 3)
            pygame.draw.circle(surf, paint.shade(c, 0.55), (hx, hy), 3.2)
            pygame.draw.circle(surf, c, (hx, hy), 2.7)
            pygame.draw.polygon(surf, (230, 160, 40), [(hx + f * 2, hy - 1), (hx + f * 5, hy), (hx + f * 2, hy + 1)])
            pygame.draw.polygon(surf, (200, 40, 40), [(hx - 1, hy - 2.5), (hx + 0.5, hy - 5), (hx + 2, hy - 2)])
            pygame.draw.circle(surf, (190, 40, 40), (hx + f * 1.5, hy + 2.5), 1.0)
            pygame.draw.circle(surf, (20, 20, 20), (hx + f, hy - 1), 0.9)
            return
        pygame.draw.ellipse(surf, c, (cx - self.w / 2, fy - self.h, self.w, self.h))


def stride_len(species, speed):
    sp = SPEC.get(species)
    if sp is None:
        return 30.0
    L = sp["L"]
    return L * (1.1 if speed < L * 1.9 else 1.6 if speed < L * 3.2 else 2.4)


def draw_horse(surf, cx, fy, f, ph, color, moving, dead=False, gallop=False, saddle=False, shade=1.0):
    c = tuple(int(v * shade) for v in color)
    draw_horse_at(surf, cx, fy, f, ph, moving, gallop, coat=c)


def draw_horse_simple(surf, x, y, f, frame, shade, moving):
    draw_horse(surf, x, y, f, frame / 8.0, (120, 82, 52), moving, gallop=moving, saddle=True, shade=shade)
