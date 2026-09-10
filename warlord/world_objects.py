"""Interactive structures and resources in the overworld."""

import random

import pygame

from .config import DARK_GRAY, GOLD, GROUND_BASE, HEIGHT, MAX_WHEAT, WHEAT_COLOR, WIDTH
from .terrain import ground_y


class Wall:
    def __init__(self, x):
        self.x, self.w, self.h = x, 24, 90
        self.built = False
        self.max_durability = 150
        self.durability = 0
        self.door_state = "closed"
        self.locked = False

    @property
    def is_solid(self):
        return self.built and self.door_state != "open"

    @property
    def rect(self):
        gy = ground_y(self.x)
        return pygame.Rect(int(self.x - self.w / 2), int(gy - self.h), self.w, self.h)

    def build(self):
        self.built, self.durability = True, self.max_durability
        self.door_state = "closed"

    def toggle_door(self):
        if not self.built:
            return "unbuilt"
        if self.locked:
            return "locked"
        self.door_state = "open" if self.door_state == "closed" else "closed"
        return self.door_state

    def take_damage(self, damage):
        if self.built:
            self.durability -= damage
            if self.durability <= 0:
                self.built, self.durability = False, 0

    def draw(self, surf, camera_x):
        rect = self.rect.move(-int(camera_x), 0)
        if self.built:
            pct = self.durability / self.max_durability
            if self.door_state == "open":
                pygame.draw.rect(surf, (90, 70, 50), rect, 2, border_radius=3)
                pygame.draw.line(surf, (140, 100, 60), rect.midtop, rect.midbottom, 4)
            else:
                pygame.draw.rect(surf, (140 + int(60 * pct), 90, 60), rect, border_radius=3)
            bar = pygame.Rect(rect.x, rect.y - 10, rect.w, 5)
            pygame.draw.rect(surf, DARK_GRAY, bar)
            pygame.draw.rect(surf, GOLD, (bar.x, bar.y, int(bar.w * pct), bar.h))
        else:
            pygame.draw.rect(surf, (90, 70, 50), rect, 2, border_radius=3)


class FarmPatch:
    STAGES = 4

    def __init__(self, x):
        self.x, self.w = x, 90
        self.stage, self.timer = 0, 0.0
        self.grow_time = 6.0
        self.ready = False

    def update(self, dt):
        if self.stage < self.STAGES - 1:
            self.timer += dt
            if self.timer >= self.grow_time:
                self.timer, self.stage = 0, self.stage + 1
                if self.stage == self.STAGES - 1:
                    self.ready = True

    def harvest(self):
        if self.ready:
            self.stage, self.ready, self.timer = 0, False, 0
            return random.randint(2, 4)
        return 0

    @property
    def rect(self):
        gy = ground_y(self.x)
        return pygame.Rect(int(self.x - self.w / 2), int(gy - 18), self.w, 18)

    def draw(self, surf, camera_x):
        rect = self.rect.move(-int(camera_x), 0)
        pygame.draw.rect(surf, (90, 60, 35), rect)
        for index in range(6):
            x = rect.x + (index + 0.5) * rect.w / 6
            height = 4 + self.stage * 6
            color = WHEAT_COLOR if self.stage == self.STAGES - 1 else (110, 140, 60)
            pygame.draw.line(surf, color, (x, rect.y), (x, rect.y - height), 3)


class Market:
    def __init__(self, x):
        self.x, self.w = x, 50
        self.base_price = 10.0
        self.price = 10.0
        self.recover_rate = 0.6

    @property
    def rect(self):
        gy = ground_y(self.x)
        return pygame.Rect(int(self.x - self.w / 2), int(gy - 60), self.w, 60)

    def update(self, dt):
        if self.price < self.base_price:
            self.price = min(self.base_price, self.price + self.recover_rate * dt)

    def sell(self, amount):
        total = 0
        for _ in range(amount):
            total += self.price
            self.price = max(2.0, self.price * 0.92)
        return round(total)

    def draw(self, surf, camera_x):
        rect = self.rect.move(-int(camera_x), 0)
        pygame.draw.rect(surf, (150, 120, 70), rect)
        pygame.draw.polygon(surf, (110, 80, 50), [(rect.x - 6, rect.y), (rect.centerx, rect.y - 22), (rect.right + 6, rect.y)])


class Tent:
    def __init__(self, x):
        self.x, self.w, self.h = x, 70, 55

    @property
    def rect(self):
        gy = ground_y(self.x)
        return pygame.Rect(int(self.x - self.w / 2), int(gy - self.h), self.w, self.h)

    def draw(self, surf, camera_x):
        rect = self.rect.move(-int(camera_x), 0)
        pygame.draw.polygon(surf, (150, 60, 50), [(rect.x, rect.bottom), (rect.centerx, rect.top), (rect.right, rect.bottom)])
        pygame.draw.polygon(surf, (100, 40, 35), [(rect.centerx - 14, rect.bottom), (rect.centerx, rect.top + 16), (rect.centerx + 14, rect.bottom)])


class House:
    def __init__(self, x, name):
        self.x = x
        self.name = name
        self.w, self.h = 110, 85
        self.interior_bounds = (95, WIDTH - 95)
        self.interior_points = {"door": 130, "bed": 390, "table": 595, "storage": 785}

    @property
    def rect(self):
        gy = ground_y(self.x)
        return pygame.Rect(int(self.x - self.w / 2), int(gy - self.h), self.w, self.h)

    def draw(self, surf, camera_x):
        rect = self.rect.move(-int(camera_x), 0)
        pygame.draw.rect(surf, (116, 78, 48), rect)
        pygame.draw.polygon(surf, (75, 45, 35), [(rect.x - 10, rect.y), (rect.centerx, rect.y - 38), (rect.right + 10, rect.y)])
        pygame.draw.rect(surf, (45, 30, 25), (rect.centerx - 12, rect.bottom - 35, 24, 35))
        pygame.draw.rect(surf, (190, 155, 75), (rect.x + 14, rect.y + 26, 18, 18))
        pygame.draw.rect(surf, (190, 155, 75), (rect.right - 32, rect.y + 26, 18, 18))

    def draw_interior(self, surf):
        surf.fill((43, 34, 32))
        pygame.draw.rect(surf, (117, 82, 55), (70, 110, WIDTH - 140, HEIGHT - 160))
        pygame.draw.rect(surf, (78, 54, 42), (70, 110, WIDTH - 140, 12))
        pygame.draw.rect(surf, (56, 40, 34), (70, GROUND_BASE, WIDTH - 140, 12))
        pygame.draw.rect(surf, (47, 31, 25), (105, HEIGHT - 122, 48, 60))
        floor_y = GROUND_BASE
        pygame.draw.rect(surf, (150, 58, 55), (335, floor_y - 48, 110, 48))
        pygame.draw.rect(surf, (225, 205, 165), (345, floor_y - 64, 90, 20))
        pygame.draw.rect(surf, (92, 56, 33), (555, floor_y - 52, 90, 14))
        pygame.draw.line(surf, (92, 56, 33), (570, floor_y - 38), (570, floor_y), 5)
        pygame.draw.line(surf, (92, 56, 33), (630, floor_y - 38), (630, floor_y), 5)
        pygame.draw.rect(surf, (72, 48, 32), (750, floor_y - 78, 72, 78))
        pygame.draw.rect(surf, (143, 101, 54), (760, floor_y - 63, 52, 10))


class LeashPost:
    def __init__(self, x):
        self.x = x
        self.w = 18

    @property
    def rect(self):
        gy = ground_y(self.x)
        return pygame.Rect(int(self.x - 9), int(gy - 58), 18, 58)

    def draw(self, surf, camera_x, tethered):
        rect = self.rect.move(-int(camera_x), 0)
        pygame.draw.line(surf, (88, 55, 32), (rect.centerx, rect.bottom), (rect.centerx, rect.top), 6)
        pygame.draw.circle(surf, GOLD if tethered else (145, 105, 65), (rect.centerx, rect.top), 7, 2)


class Horse:
    def __init__(self, x):
        self.x = x
        self.facing = 1
        self.w, self.h = 72, 52
        self.speed = 340
        self.mounted = False
        self.tethered = False
        self.post_x = None
        self.inventory_wheat = 0
        self.animation_time = 0.0

    @property
    def rect(self):
        gy = ground_y(self.x)
        return pygame.Rect(int(self.x - self.w / 2), int(gy - self.h), self.w, self.h)

    def update(self, dt, player):
        self.animation_time += dt
        if self.mounted:
            self.x = player.x
            self.facing = player.facing
        elif self.tethered and self.post_x is not None:
            self.x = self.post_x

    def draw(self, surf, camera_x):
        rect = self.rect.move(-int(camera_x), 0)
        leg_sway = int(__import__("math").sin(self.animation_time * 5) * 2)
        body = pygame.Rect(rect.x + 8, rect.y + 16, 52, 28)
        pygame.draw.ellipse(surf, (112, 70, 42), body)
        neck = [(rect.x + 48, rect.y + 23), (rect.x + 58, rect.y - 6), (rect.x + 70, rect.y - 2), (rect.x + 60, rect.y + 27)]
        pygame.draw.polygon(surf, (112, 70, 42), neck)
        pygame.draw.circle(surf, (112, 70, 42), (rect.x + 69, rect.y - 4), 9)
        pygame.draw.circle(surf, (20, 20, 20), (rect.x + 72, rect.y - 6), 2)
        pygame.draw.line(surf, (72, 45, 30), (rect.x + 18, rect.bottom - 8), (rect.x + 14, rect.bottom + leg_sway), 6)
        pygame.draw.line(surf, (72, 45, 30), (rect.x + 50, rect.bottom - 8), (rect.x + 54, rect.bottom - leg_sway), 6)
        if self.mounted:
            pygame.draw.rect(surf, (120, 35, 30), (rect.centerx - 18, rect.y + 10, 36, 8))
