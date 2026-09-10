"""
WARLORD 2D - prototype v2

New in this version:
  - jump (Space when idle/walking; Space while running still slides)
  - rolling hill/depression terrain instead of a flat floor
  - a camera that follows the player across a wider world
  - multiple enemies: press N to spawn one near you, whenever you want
  - enemy vision: each enemy only notices you if you're within its vision
    range AND it's facing your side; until then it just stands/looks around

Controls:
  A/D or Left/Right   : move
  Hold Shift           : run
  Hold S / Down        : crouch
  Space                : jump (grounded, not running) / slide (grounded, running)
  J                    : attack (type depends on current state)
    Hold Q, release Q    : draw and fire a bow
  K                    : hold to block / tap right before a hit lands to parry
    E                    : select a nearby recruit, or interact with world objects
    R                    : recruit a weakened enemy nearby (10g)
    1 / 2 / 3             : selected recruit guard / follow / charge
  N                    : spawn a new enemy near the player
  Esc                  : back to menu / quit
"""

import pygame
import math
import random
import sys

from warlord.config import *
from warlord.terrain import WorldLayout, ground_y

pygame.init()

screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Warlord 2D - Prototype")
clock = pygame.time.Clock()
font_big = pygame.font.SysFont("consolas", 44, bold=True)
font_med = pygame.font.SysFont("consolas", 22, bold=True)
font_small = pygame.font.SysFont("consolas", 16)



class Arrow:
    """A world-space arrow with an arcing trajectory and one-hit impact."""

    def __init__(self, x, z, facing, charge, owner, aim_angle=0.0):
        self.x = float(x)
        self.origin_x = self.x
        self.z = float(z)
        strength = max(MIN_STRENGTH, min(MAX_STRENGTH, owner.strength))
        launch_speed = math.hypot(420 + 420 * charge, 70 + 150 * charge) * strength
        self.vx = facing * launch_speed * math.cos(aim_angle)
        self.world_y = ground_y(self.x) - self.z
        self.vy = -launch_speed * math.sin(aim_angle)
        self.facing = facing
        self.damage = int((12 + 28 * charge) * strength)
        self.owner = owner
        self.alive = True
        self.floor_y = None
        self.stuck = False
        self.stuck_target = None
        self.stuck_offset_x = 0.0
        self.stuck_offset_z = 0.0
        self.angle = math.atan2(-self.vy, self.vx)

    @property
    def rect(self):
        point_x = self.x + math.cos(self.angle) * 16
        point_y = self.world_y - math.sin(self.angle) * 16
        point_radius = 3
        return pygame.Rect(
            int(point_x - point_radius),
            int(point_y - point_radius),
            point_radius * 2,
            point_radius * 2,
        )

    def update(self, dt):
        if self.stuck:
            if self.stuck_target is not None:
                if not self.stuck_target.alive and self.stuck_target.death_timer <= 0:
                    self.alive = False
                    return
                self.x = self.stuck_target.x + self.stuck_offset_x
                self.z = self.stuck_target.z + self.stuck_offset_z
                if not self.stuck_target.alive:
                    progress = 1.0 - self.stuck_target.death_timer / self.stuck_target.death_duration
                    self.x += self.stuck_target.facing * 30 * progress
                    self.z -= 43 * progress
                self.world_y = ground_y(self.x) - self.z
            return
        self.x += self.vx * dt
        self.vy += GRAVITY * 0.72 * dt
        self.world_y += self.vy * dt
        self.angle = math.atan2(-self.vy, self.vx)
        floor_y = self.floor_y if self.floor_y is not None else ground_y(self.x)
        if self.world_y >= floor_y:
            self.world_y = floor_y
            self.z = 0.0
            self.stuck = True
        elif self.x < 0 or self.x > WORLD_WIDTH:
            self.alive = False

    def stick_to(self, target=None):
        self.stuck = True
        self.stuck_target = target
        if target is not None:
            self.stuck_offset_x = self.x - target.x
            self.stuck_offset_z = self.z - target.z

    def draw(self, surf, camera_x):
        if not self.alive:
            return
        x = int(self.x - camera_x)
        y = int(self.world_y)
        direction_x = math.cos(self.angle)
        direction_y = -math.sin(self.angle)
        normal_x, normal_y = -direction_y, direction_x
        shaft_length = 16
        dx = direction_x * shaft_length
        dy = direction_y * shaft_length
        tail = (int(x - dx), int(y - dy))
        tip = (int(x + dx), int(y + dy))
        point_base = (int(tip[0] - direction_x * 5), int(tip[1] - direction_y * 5))
        pygame.draw.line(surf, (92, 58, 32), tail, point_base, 2)
        feather_base = (int(tail[0] + direction_x * 5), int(tail[1] + direction_y * 5))
        feather_tip = (int(tail[0] - direction_x * 5), int(tail[1] - direction_y * 5))
        pygame.draw.line(
            surf, (150, 125, 90), feather_base,
            (int(feather_tip[0] + normal_x * 3), int(feather_tip[1] + normal_y * 3)), 1,
        )
        pygame.draw.line(
            surf, (150, 125, 90), feather_base,
            (int(feather_tip[0] - normal_x * 3), int(feather_tip[1] - normal_y * 3)), 1,
        )
        pygame.draw.polygon(
            surf, (175, 180, 185),
            [tip,
             (int(point_base[0] + normal_x * 3), int(point_base[1] + normal_y * 3)),
             (int(point_base[0] - normal_x * 3), int(point_base[1] - normal_y * 3))],
        )


# ---------------------------------------------------------------- Fighter --
class Fighter:
    """Shared combat/movement rules used by BOTH the player and every enemy,
    so all AI fighters obey the exact same ruleset as the player."""

    def __init__(self, x, color, facing=1):
        self.x = x
        self.color = color
        self.facing = facing

        self.vx = 0
        self.state = "idle"  # idle, walk, run, crouch, slide, air, stun
        self.walk_speed = 140
        self.run_speed = 260
        self.slide_speed = 380
        self.slide_timer = 0.0
        self.slide_duration = 0.35

        # vertical / jump physics
        self.z = 0.0          # height above the ground at this x
        self.vz = 0.0
        self.on_ground = True

        self.h = 70
        self.w = 34

        self.health = 100
        self.max_health = 100
        self.stamina = 100
        self.max_stamina = 100
        self.stamina_regen = 18
        self.strength = MIN_STRENGTH

        self.attack_cooldown = 0.0
        self.attacking = False
        self.attack_timer = 0.0
        self.attack_duration = 0.56
        self.attack_type = None  # base / thrust / counter
        self.hitbox = None
        self.has_hit = False

        self.blocking = False
        self.parry_window = 0.0
        self.parry_buffer = 0.15
        self.parry_stun_duration = 0.8
        self.stunned_timer = 0.0
        self.counter_stance_timer = 0.0
        self.head_bob_timer = 0.0
        self.animation_time = 0.0
        self.sword_drawn = False
        self.sword_idle_timer = 0.0
        self.sheathing_timer = 0.0

        self.alive = True
        self.death_duration = 1.4
        self.death_timer = 0.0
        self.floor_y = None

    @property
    def rect(self):
        size = self.size_multiplier
        h = self.h * 0.55 if self.state in ("crouch", "slide") else self.h
        h *= size
        w = self.w * size
        base_y = self.floor_y if self.floor_y is not None else ground_y(self.x)
        gy = base_y - self.z
        return pygame.Rect(int(self.x - w / 2), int(gy - h), int(w), int(h))

    @property
    def size_multiplier(self):
        strength = max(MIN_STRENGTH, min(MAX_STRENGTH, self.strength))
        return 1.0 + (strength - MIN_STRENGTH) * (MAX_SIZE_MULTIPLIER - 1.0)

    def is_locked(self):
        return self.stunned_timer > 0

    def update_physics(self, dt):
        """Gravity / jump arc. z is height above the terrain at this x."""
        self.animation_time += dt
        if not self.alive:
            return
        if self.z > 0 or self.vz != 0:
            self.vz -= GRAVITY * dt
            self.z += self.vz * dt
            if self.z <= 0:
                self.z = 0.0
                self.vz = 0.0
                self.on_ground = True
        else:
            self.on_ground = True

    def start_attack(self):
        if (not self.alive or self.attack_cooldown > 0 or self.attacking
                or self.is_locked() or self.blocking):
            return
        if self.state == "run":
            self.attack_type, cost = "thrust", 18
        elif self.state == "crouch":
            self.attack_type, cost = "counter", 10
            self.counter_stance_timer = 0.25
        else:
            self.attack_type, cost = "base", 12
        if self.stamina < cost:
            return
        self.attack_duration = 0.32 if self.attack_type in ("thrust", "counter") else 0.56
        self.stamina -= cost
        self.attacking = True
        self.sheathing_timer = 0.0
        self.attack_timer = self.attack_duration
        self.has_hit = False
        self.attack_cooldown = 0.42

    def update_attack(self, dt):
        if self.attack_cooldown > 0:
            self.attack_cooldown -= dt
        if self.counter_stance_timer > 0:
            self.counter_stance_timer -= dt
        if self.attacking:
            self.attack_timer -= dt
            reach = {"thrust": 55, "counter": 49}.get(self.attack_type, 49)
            body_h = self.h * 0.55 if self.state in ("crouch", "slide") else self.h
            base_y = self.floor_y if self.floor_y is not None else ground_y(self.x)
            gy = base_y - self.z
            hy = gy - body_h
            hx = self.x + self.facing * (self.w / 2)
            progress = 1.0 - max(0.0, self.attack_timer) / self.attack_duration
            damage_start = 0.12 if self.attack_type in ("thrust", "counter") else 0.62
            if progress >= damage_start:
                self.hitbox = pygame.Rect(
                    int(hx if self.facing > 0 else hx - reach),
                    int(hy),
                    int(reach),
                    int(body_h * 0.7),
                )
            else:
                self.hitbox = None
            if self.attack_timer <= 0:
                self.attacking = False
                self.hitbox = None
                self.sword_drawn = True
                self.sword_idle_timer = 3.0
        else:
            self.hitbox = None
            if self.sword_drawn and self.sheathing_timer <= 0:
                self.sword_idle_timer -= dt
                if self.sword_idle_timer <= 0:
                    self.sheathing_timer = 0.24
            if self.sheathing_timer > 0:
                self.sheathing_timer -= dt
                if self.sheathing_timer <= 0:
                    self.sheathing_timer = 0.0
                    self.sword_drawn = False

    def damage_of_current_attack(self):
        base_damage = {"base": 14, "thrust": 22, "counter": 26}.get(self.attack_type, 10)
        return base_damage * self.strength

    def attack_in_windup(self):
        if not self.attacking:
            return False
        progress = 1.0 - max(0.0, self.attack_timer) / self.attack_duration
        damage_start = 0.12 if self.attack_type in ("thrust", "counter") else 0.62
        return progress < damage_start

    def try_block(self, held, just_pressed):
        if not self.alive or self.is_locked():
            self.blocking = False
            return
        self.blocking = held and self.state not in ("run", "slide", "air") and self.stamina > 0
        if just_pressed:
            self.parry_window = self.parry_buffer

    def update_defense_timers(self, dt):
        if self.parry_window > 0:
            self.parry_window -= dt
        if self.stunned_timer > 0:
            self.stunned_timer -= dt
        if self.head_bob_timer > 0:
            self.head_bob_timer -= dt

    def take_hit(self, attacker):
        if not self.alive:
            return "already down"
        dmg = attacker.damage_of_current_attack()
        if self.counter_stance_timer > 0:
            attacker.stunned_timer = attacker.parry_stun_duration
            attacker.attacking = False
            attacker.hitbox = None
            attacker.blocking = False
            attacker.vx = 0
            attacker.state = "stun"
            self.counter_stance_timer = 0
            return "countered"
        if self.parry_window > 0 and attacker.attack_in_windup():
            attacker.stunned_timer = attacker.parry_stun_duration
            attacker.attacking = False
            attacker.hitbox = None
            attacker.blocking = False
            attacker.vx = 0
            attacker.state = "stun"
            self.parry_window = 0
            return "parried"
        if self.blocking and self.stamina > 0:
            self.stamina -= dmg * 0.6
            self.health -= dmg * 0.15
            if self.stamina <= 0:
                self.stamina = 0
                self.stunned_timer = 0.7
            return "blocked"
        self.health -= dmg
        if self.health <= 0:
            self.die()
        return "hit"

    def die(self):
        if not self.alive:
            return
        self.health = 0
        self.alive = False
        self.state = "dead"
        self.death_timer = self.death_duration
        self.vx = 0
        self.vz = 0
        self.attacking = False
        self.blocking = False
        self.hitbox = None
        if hasattr(self, "bow_charge"):
            self.bow_charge = 0.0

    def update_death(self, dt):
        if not self.alive and self.death_timer > 0:
            self.death_timer = max(0.0, self.death_timer - dt)

    def regen(self, dt):
        if not self.blocking:
            self.stamina = min(self.max_stamina, self.stamina + self.stamina_regen * dt)

    def draw(self, surf, camera_x):
        if not self.alive:
            self.draw_corpse(surf, camera_x)
            return
        r = self.rect.move(-int(camera_x), 0)
        moving = self.state in ("walk", "run", "slide") and abs(self.vx) > 1
        stride_speed = 13 if self.state == "run" else 9
        stride = math.sin(self.animation_time * stride_speed) if moving else 0
        limb_color = tuple(max(0, channel - 45) for channel in self.color)
        skin_color = (215, 170, 130)
        size = self.size_multiplier
        arm_width = max(1, int(8 * size))
        narrow_arm_width = max(1, int(7 * size))
        hand_radius = max(2, int(5 * size))
        elbow_radius = max(2, int(4 * size))

        if self.state == "slide":
            slide_hip = (r.centerx, r.bottom - 10)
            front_knee = (r.centerx + self.facing * 16, r.bottom - 5)
            front_foot = (r.centerx + self.facing * 30, r.bottom - 1)
            back_knee = (r.centerx - self.facing * 10, r.bottom - 4)
            back_foot = (r.centerx - self.facing * 25, r.bottom - 1)
            pygame.draw.line(surf, limb_color, slide_hip, front_knee, 7)
            pygame.draw.line(surf, limb_color, front_knee, front_foot, 7)
            pygame.draw.line(surf, limb_color, slide_hip, back_knee, 7)
            pygame.draw.line(surf, limb_color, back_knee, back_foot, 7)
            left_foot, right_foot = front_foot, back_foot
        elif self.state == "crouch":
            hip_y = r.bottom - 16
            left_foot = (r.centerx - 8 + int(stride * 5), r.bottom - 2)
            right_foot = (r.centerx + 8 - int(stride * 5), r.bottom - 2)
            pygame.draw.line(surf, limb_color, (r.centerx - 6, hip_y), left_foot, 7)
            pygame.draw.line(surf, limb_color, (r.centerx + 6, hip_y), right_foot, 7)
        else:
            hip_y = r.bottom - 22
            left_foot = (r.centerx - 8 + int(stride * 7), r.bottom - 1)
            right_foot = (r.centerx + 8 - int(stride * 7), r.bottom - 1)
            pygame.draw.line(surf, limb_color, (r.centerx - 7, hip_y), left_foot, 7)
            pygame.draw.line(surf, limb_color, (r.centerx + 7, hip_y), right_foot, 7)
        pygame.draw.line(surf, (25, 25, 30), left_foot, (left_foot[0] + self.facing * 6, left_foot[1]), 4)
        pygame.draw.line(surf, (25, 25, 30), right_foot, (right_foot[0] + self.facing * 6, right_foot[1]), 4)

        body = r.copy()
        body.width = max(18, int(r.width * 0.66))
        body.height = max(24, int(r.height * 0.72))
        body.left = r.centerx - body.width // 2
        body.top = r.top + 8
        pygame.draw.rect(surf, self.color, body, border_radius=4)
        head_bob = int(math.sin(self.head_bob_timer * 32) * 3) if self.head_bob_timer > 0 else 0
        head_arc = (
            0.5
            + math.sin(self.animation_time * 0.8) * 0.28
            + math.sin(self.animation_time * 1.27 + 1.1) * 0.12
        )
        arc_lift = math.sin(head_arc * math.pi) * 1.5
        stun_recoil = math.sin(self.animation_time * 18) * 3 if self.stunned_timer > 0 else 0
        head_x = int(r.centerx + self.facing * 8 * (1.0 - head_arc) - self.facing * 3 + stun_recoil)
        head_y = int(body.top - 8 + 4 * (1.0 - head_arc) - arc_lift + head_bob - abs(stun_recoil) * 0.6)
        pygame.draw.circle(surf, self.color, (head_x, head_y), int(8 * self.size_multiplier))

        shoulder_y = body.top + 14
        lead_shoulder = (r.centerx + self.facing * 10, shoulder_y - 3)
        free_shoulder = (r.centerx - self.facing * 11, shoulder_y - 3)
        arm_swing = int(stride * (10 if self.state == "run" else 7)) if moving else 0
        free_hand = (
            free_shoulder[0] + self.facing * int(3 * size) + arm_swing,
            free_shoulder[1] + int(19 * size),
        )
        bow_drawing = getattr(self, "bow_charge", 0) > 0
        if not self.blocking and not bow_drawing:
            pygame.draw.line(surf, skin_color, free_shoulder, free_hand, arm_width)
            pygame.draw.circle(surf, skin_color, free_hand, hand_radius)
        sword_length = 49
        if self.attacking and self.attack_type == "thrust":
            sword_length = 55
        lead_hand = (lead_shoulder[0] + self.facing * 7, lead_shoulder[1] - 6)
        sheath_grip = (int(r.centerx - self.facing * 8), int(body.bottom - 15))
        sheath_arm_angle = math.atan2(
            sheath_grip[1] - lead_shoulder[1],
            (sheath_grip[0] - lead_shoulder[0]) * self.facing,
        )
        if bow_drawing:
            bow_x = r.centerx + self.facing * 18
            bow_y = r.centery - 14 - int(math.sin(self.bow_angle) * 18)
            aim_cos = math.cos(self.bow_angle)
            aim_sin = math.sin(self.bow_angle)

            def bow_point(forward, vertical):
                return (
                    int(bow_x + self.facing * (forward * aim_cos + vertical * aim_sin)),
                    int(bow_y - forward * aim_sin + vertical * aim_cos),
                )

            nock = bow_point(-(10 + 10 * self.bow_charge / MAX_BOW_CHARGE), 0)
            grip = bow_point(0, 0)
            pull_elbow = (
                int((free_shoulder[0] + nock[0]) * 0.5 - self.facing * 5),
                int((free_shoulder[1] + nock[1]) * 0.5),
            )
            pygame.draw.line(surf, skin_color, lead_shoulder, grip, arm_width)
            pygame.draw.circle(surf, skin_color, grip, hand_radius)
            pygame.draw.line(surf, skin_color, free_shoulder, pull_elbow, arm_width)
            pygame.draw.line(surf, skin_color, pull_elbow, nock, narrow_arm_width)
            pygame.draw.circle(surf, skin_color, pull_elbow, elbow_radius)
            pygame.draw.circle(surf, skin_color, nock, hand_radius)
            waist_grip = (int(r.centerx - self.facing * 8), int(body.bottom - 15))
            sheath_angle = math.radians(-4)
            sheath_tip = (
                int(waist_grip[0] - self.facing * math.cos(sheath_angle) * 48),
                int(waist_grip[1] + math.sin(sheath_angle) * 48),
            )
            pygame.draw.line(surf, (55, 45, 35), waist_grip, sheath_tip, 7)
            pygame.draw.line(surf, GOLD, waist_grip,
                             (waist_grip[0] + self.facing * 7, waist_grip[1]), 4)
        elif self.blocking:
            guard_grip = (int(r.centerx + self.facing * 5), int(body.centery - 8))
            guard_angle = math.radians(-68)
            guard_tip = (
                int(guard_grip[0] + self.facing * math.cos(guard_angle) * sword_length),
                int(guard_grip[1] + math.sin(guard_angle) * sword_length),
            )
            guard_back_hand = (guard_grip[0] - self.facing * 7, guard_grip[1] + 8)
            free_elbow = (free_shoulder[0] - self.facing * 3, free_shoulder[1] + 10)
            pygame.draw.line(surf, skin_color, lead_shoulder, guard_grip, arm_width)
            pygame.draw.line(surf, skin_color, free_shoulder, free_elbow, arm_width)
            pygame.draw.line(surf, skin_color, free_elbow, guard_back_hand, arm_width)
            pygame.draw.circle(surf, skin_color, free_elbow, elbow_radius)
            pygame.draw.circle(surf, skin_color, guard_back_hand, hand_radius)
            pygame.draw.line(surf, (35, 35, 40), guard_grip, guard_tip, 11)
            pygame.draw.line(surf, (235, 235, 245), guard_grip, guard_tip, 7)
            pygame.draw.line(surf, (255, 255, 255), guard_grip, guard_tip, 2)
            pygame.draw.circle(surf, GOLD, guard_grip, 6)
        elif self.attacking:
            progress = 1.0 - max(0.0, self.attack_timer) / self.attack_duration
            idle_arm_angle = math.radians(48 if self.sword_drawn else 55)
            draw_t = 1.0 if self.sword_drawn else min(1.0, progress / 0.2)
            sheath_t = 0.0
            swing_t = min(1.0, max(0.0, (progress - 0.2) / 0.6))
            if self.attack_type == "thrust":
                attack_arm_angle = math.radians(-6)
            elif self.attack_type == "counter":
                counter_progress = min(1.0, progress / 0.32)
                attack_arm_angle = math.radians(65 - counter_progress * 145)
            elif progress < 0.62:
                charge_t = progress / 0.62
                attack_arm_angle = math.radians(55 - charge_t * 165)
            else:
                release_t = (progress - 0.62) / 0.38
                attack_arm_angle = math.radians(-110 + release_t * 150)
            arm_angle = idle_arm_angle + (attack_arm_angle - idle_arm_angle) * draw_t
            if not self.sword_drawn:
                arm_angle = sheath_arm_angle + (attack_arm_angle - sheath_arm_angle) * draw_t
            upper_arm_angle = arm_angle
            forearm_angle = arm_angle
            if self.attack_type == "base" and progress < 0.62:
                charge_t = progress / 0.62
                upper_arm_angle = math.radians(55 - charge_t * 235)
                forearm_angle = math.radians(-25 - charge_t * 100)
                if not self.sword_drawn:
                    upper_arm_angle = sheath_arm_angle + (upper_arm_angle - sheath_arm_angle) * draw_t
                    forearm_angle = sheath_arm_angle + (forearm_angle - sheath_arm_angle) * draw_t
            upper_arm_length = int(10 * size)
            forearm_length = int(16 * size)
            lead_elbow = (
                int(lead_shoulder[0] + self.facing * math.cos(upper_arm_angle) * upper_arm_length),
                int(lead_shoulder[1] + math.sin(upper_arm_angle) * upper_arm_length),
            )
            lead_hand = (
                int(lead_elbow[0] + self.facing * math.cos(forearm_angle) * forearm_length),
                int(lead_elbow[1] + math.sin(forearm_angle) * forearm_length),
            )
            pygame.draw.line(surf, skin_color, lead_shoulder, lead_elbow, arm_width)
            pygame.draw.line(surf, skin_color, lead_elbow, lead_hand, arm_width)
            pygame.draw.circle(surf, skin_color, lead_elbow, elbow_radius)
            sword_grip = lead_hand
            attack_blade_angle = forearm_angle - math.radians(10)
            angle = math.radians(-4) + (attack_blade_angle - math.radians(-4)) * draw_t
            tip = (
                int(sword_grip[0] + self.facing * math.cos(angle) * sword_length),
                int(sword_grip[1] + math.sin(angle) * sword_length),
            )
            pygame.draw.line(surf, (35, 35, 40), sword_grip, tip, 12)
            pygame.draw.line(surf, (235, 235, 245), sword_grip, tip, 7)
            pygame.draw.line(surf, (255, 255, 255), sword_grip, tip, 2)
            pygame.draw.circle(surf, GOLD, lead_hand, 6)
        elif self.sheathing_timer > 0:
            sheathe_t = 1.0 - self.sheathing_timer / 0.24
            arm_angle = math.radians(48) + (sheath_arm_angle - math.radians(48)) * sheathe_t
            upper_arm_length = int(10 * size)
            forearm_length = int(16 * size)
            lead_elbow = (
                int(lead_shoulder[0] + self.facing * math.cos(arm_angle) * upper_arm_length),
                int(lead_shoulder[1] + math.sin(arm_angle) * upper_arm_length),
            )
            lead_hand = (
                int(lead_elbow[0] + self.facing * math.cos(arm_angle) * forearm_length),
                int(lead_elbow[1] + math.sin(arm_angle) * forearm_length),
            )
            sword_grip = lead_hand
            sword_angle = math.radians(-4)
            sword_tip = (
                int(sword_grip[0] + self.facing * math.cos(sword_angle) * sword_length),
                int(sword_grip[1] + math.sin(sword_angle) * sword_length),
            )
            pygame.draw.line(surf, skin_color, lead_shoulder, lead_elbow, arm_width)
            pygame.draw.line(surf, skin_color, lead_elbow, lead_hand, arm_width)
            pygame.draw.circle(surf, skin_color, lead_elbow, elbow_radius)
            pygame.draw.line(surf, (200, 200, 210), sword_grip, sword_tip, 5)
            pygame.draw.line(surf, GOLD, sword_grip,
                             (sword_grip[0] + self.facing * 7, sword_grip[1]), 4)
        else:
            idle_sway = math.sin(self.animation_time * 2.2) if self.state == "idle" else 0
            walk_swing = stride * (6 if self.sword_drawn else 8) if moving else 0
            stun_swing = math.sin(self.animation_time * 18) * 18 if self.stunned_timer > 0 else 0
            if self.sword_drawn:
                if self.stunned_timer > 0:
                    arm_angle = math.radians(270 + stun_swing * 0.2)
                else:
                    arm_angle = math.radians(48 + idle_sway * 5 + walk_swing)
            else:
                arm_angle = math.radians(55 + idle_sway * 3 + walk_swing + stun_swing)
            upper_arm_length = int(10 * size)
            forearm_length = int(16 * size)
            lead_elbow = (
                int(lead_shoulder[0] + self.facing * math.cos(arm_angle) * upper_arm_length),
                int(lead_shoulder[1] + math.sin(arm_angle) * upper_arm_length),
            )
            lead_hand = (
                int(lead_elbow[0] + self.facing * math.cos(arm_angle) * forearm_length),
                int(lead_elbow[1] + math.sin(arm_angle) * forearm_length),
            )
            pygame.draw.line(surf, skin_color, lead_shoulder, lead_elbow, arm_width)
            pygame.draw.line(surf, skin_color, lead_elbow, lead_hand, arm_width)
            pygame.draw.circle(surf, skin_color, lead_elbow, elbow_radius)
            if self.stunned_timer > 0:
                pygame.draw.rect(surf, self.color, body, border_radius=4)
            if self.sword_drawn:
                if self.stunned_timer > 0:
                    sword_angle = math.radians(270 + stun_swing * 0.15)
                else:
                    sword_angle = math.radians(-4 + idle_sway * 5 + walk_swing * 0.45)
                sword_tip = (
                    int(lead_hand[0] + self.facing * math.cos(sword_angle) * sword_length),
                    int(lead_hand[1] + math.sin(sword_angle) * sword_length),
                )
                pygame.draw.line(surf, (200, 200, 210), lead_hand, sword_tip, 5)
                pygame.draw.line(surf, GOLD, lead_hand,
                                 (lead_hand[0] + self.facing * 7, lead_hand[1]), 4)
            else:
                waist_grip = (int(r.centerx - self.facing * 8), int(body.bottom - 15))
                sheath_angle = math.radians(-4 + idle_sway * 3)
                sheath_tip = (
                        int(waist_grip[0] - self.facing * math.cos(sheath_angle) * 48),
                    int(waist_grip[1] + math.sin(sheath_angle) * 48),
                )
                pygame.draw.line(surf, (55, 45, 35), waist_grip, sheath_tip, 7)
                pygame.draw.line(surf, GOLD, waist_grip,
                                     (waist_grip[0] + self.facing * 7, waist_grip[1]), 4)
        if self.stunned_timer > 0:
            stun_wobble = math.sin(self.animation_time * 22) * 3
            effect_center = (int(r.centerx + stun_wobble), r.top - 21)
            pygame.draw.arc(surf, (255, 230, 0),
                            pygame.Rect(effect_center[0] - 13, effect_center[1] - 9, 26, 18),
                            0.2, 2.9, 3)
            for index in range(3):
                angle = self.animation_time * 9 + index * math.tau / 3
                spark_start = (
                    int(effect_center[0] + math.cos(angle) * 8),
                    int(effect_center[1] + math.sin(angle) * 6),
                )
                spark_end = (
                    int(effect_center[0] + math.cos(angle) * 15),
                    int(effect_center[1] + math.sin(angle) * 11),
                )
                pygame.draw.line(surf, (255, 245, 90), spark_start, spark_end, 3)
            pygame.draw.circle(surf, (255, 230, 0), effect_center, 4)

    def draw_corpse(self, surf, camera_x):
        progress = 1.0 - self.death_timer / self.death_duration
        progress = max(0.0, min(1.0, progress))
        size = self.size_multiplier
        base_y = self.floor_y if self.floor_y is not None else ground_y(self.x)
        ground = int(base_y)
        center_x = int(self.x - camera_x)
        body_length = self.h * size * 0.58
        head_radius = max(5, int(8 * size))
        limb_width = max(4, int(7 * size))
        arm_width = max(4, int(6 * size))
        hip = (center_x, ground - int(13 * size))
        head_x = int(center_x + self.facing * body_length * 0.7 * progress)
        head_y = int(ground - body_length * 0.95 + body_length * 0.72 * progress)
        torso = (head_x, head_y + int(9 * size))
        limb_color = tuple(max(0, channel - 45) for channel in self.color)
        skin_color = (215, 170, 130)

        foot_spread = self.w * size * 0.42
        pygame.draw.line(surf, limb_color, hip, (int(center_x - foot_spread), ground - int(2 * size)), limb_width)
        pygame.draw.line(surf, limb_color, hip, (int(center_x + foot_spread), ground - int(2 * size)), limb_width)
        pygame.draw.line(surf, self.color, hip, torso, max(8, int(13 * size)))
        pygame.draw.line(surf, skin_color, torso,
                         (head_x - int(self.facing * 7 * size), head_y + int(15 * size)), arm_width)
        pygame.draw.circle(surf, self.color, (head_x, head_y), head_radius)
        pygame.draw.line(surf, skin_color, (head_x, head_y + head_radius),
                         (head_x + int(self.facing * 16 * size), head_y + int(16 * size)), arm_width)


# ----------------------------------------------------------------- Player --
class Player(Fighter):
    def __init__(self, x):
        super().__init__(x, (80, 150, 220))
        self.parry_buffer = 0.28
        self.wheat = 0
        self.stored_wheat = 0
        self.money = 20
        self.bow_charge = 0.0
        self.bow_angle = 0.0
        self.mounted = False
        self.mount = None

    def draw(self, surf, camera_x):
        if not self.alive:
            super().draw(surf, camera_x)
            return
        r = self.rect.move(-int(camera_x), 0)
        sack_center_x = r.centerx - self.facing * 12
        sack_rect = pygame.Rect(sack_center_x - 10, r.top + 20, 20, 29)
        pygame.draw.ellipse(surf, (45, 32, 25), sack_rect.inflate(4, 4))
        pygame.draw.ellipse(surf, (115, 75, 40), sack_rect)
        fill_height = int((sack_rect.height - 4) * min(self.wheat, MAX_WHEAT) / MAX_WHEAT)
        if fill_height > 0:
            fill_rect = pygame.Rect(
                sack_rect.left + 3,
                sack_rect.bottom - 3 - fill_height,
                sack_rect.width - 6,
                fill_height,
            )
            pygame.draw.rect(surf, WHEAT_COLOR, fill_rect)
        pygame.draw.line(
            surf,
            (75, 48, 28),
            (sack_rect.left + 3, sack_rect.top + 5),
            (sack_rect.right - 3, sack_rect.top + 5),
            2,
        )
        super().draw(surf, camera_x)
        if self.bow_charge > 0:
            r = self.rect.move(-int(camera_x), 0)
            bow_x = r.centerx + self.facing * 18
            bow_y = r.centery - 14 - int(math.sin(self.bow_angle) * 18)
            bow_height = 30
            charge_ratio = self.bow_charge / MAX_BOW_CHARGE

            def bow_point(forward, vertical):
                cos_angle = math.cos(self.bow_angle)
                sin_angle = math.sin(self.bow_angle)
                return (
                    int(bow_x + self.facing * (forward * cos_angle + vertical * sin_angle)),
                    int(bow_y - forward * sin_angle + vertical * cos_angle),
                )

            top = bow_point(0, -bow_height)
            bottom = bow_point(0, bow_height)
            curve = bow_point(14, 0)
            pygame.draw.lines(surf, (125, 80, 42), False, [top, curve, bottom], 5)
            nock = bow_point(-(10 + 10 * charge_ratio), 0)
            arrow_guide = bow_point(20, 0)
            pygame.draw.line(surf, (225, 215, 190), top, nock, 2)
            pygame.draw.line(surf, (225, 215, 190), nock, bottom, 2)
            pygame.draw.line(surf, (225, 215, 190), nock, arrow_guide, 2)

    def update_bow(self, held, dt, aim_delta=0.0):
        if held and not self.is_locked() and not self.attacking and self.state not in ("run", "slide", "air"):
            strength = max(MIN_STRENGTH, min(MAX_STRENGTH, self.strength))
            self.bow_charge = min(MAX_BOW_CHARGE, self.bow_charge + dt * strength)
            self.bow_angle = max(
                math.radians(-55),
                min(math.radians(55), self.bow_angle + aim_delta * dt),
            )
            self.blocking = False
        elif not held and self.bow_charge > 0:
            charge = self.bow_charge / MAX_BOW_CHARGE
            self.bow_charge = 0.0
            arrow = Arrow(
                self.x + self.facing * 22 * math.cos(self.bow_angle),
                self.z + 42 + 22 * math.sin(self.bow_angle),
                          self.facing, charge, self, self.bow_angle)
            self.bow_angle = 0.0
            return arrow
        return None

    def handle_input(self, keys, dt):
        if not self.alive:
            self.vx = 0
            return
        if self.is_locked():
            self.vx = 0
            self.state = "stun"
            return

        left = keys[pygame.K_a] or keys[pygame.K_LEFT]
        right = keys[pygame.K_d] or keys[pygame.K_RIGHT]

        if not self.on_ground:
            self.state = "air"
            if left:
                self.facing, self.vx = -1, -self.walk_speed
            elif right:
                self.facing, self.vx = 1, self.walk_speed
            else:
                self.vx = 0
            self.x = max(30, min(WORLD_WIDTH - 30, self.x + self.vx * dt))
            return

        if self.slide_timer > 0:
            self.slide_timer -= dt
            self.state = "slide"
            self.vx = self.facing * self.slide_speed
            self.x = max(30, min(WORLD_WIDTH - 30, self.x + self.vx * dt))
            if self.slide_timer <= 0:
                self.state = "idle"
            return

        run = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        crouch = (keys[pygame.K_s] or keys[pygame.K_DOWN]) and self.bow_charge <= 0
        moving = left or right
        mounted_speed = self.mount.speed if self.mounted and self.mount is not None else None

        if crouch and not moving:
            self.state, self.vx = "crouch", 0
        elif moving:
            self.facing = -1 if left else 1
            if mounted_speed is not None:
                self.state, self.vx = "run", self.facing * mounted_speed
            elif run:
                self.state, self.vx = "run", self.facing * self.run_speed
            else:
                self.state, self.vx = "walk", self.facing * self.walk_speed
        else:
            self.state, self.vx = "idle", 0

        self.x = max(30, min(WORLD_WIDTH - 30, self.x + self.vx * dt))

    def try_slide(self):
        if self.on_ground and self.state == "run" and self.slide_timer <= 0 and self.stamina >= 15:
            self.slide_timer = self.slide_duration
            self.stamina -= 15

    def jump(self):
        if self.on_ground:
            self.vz = JUMP_SPEED
            self.on_ground = False

    def jump_or_slide(self):
        """Space is context-sensitive: it slides you if you're sprinting,
        otherwise it's a jump - same 'one button, state decides result'
        idea as the attack system."""
        if self.state == "run" and self.on_ground:
            self.try_slide()
        elif self.on_ground:
            self.jump()


# ------------------------------------------------------------------ Enemy --
class Enemy(Fighter):
    """Dummy AI: identical Fighter ruleset to the player. Before noticing the
    player it just idles/looks around; it only starts fighting once the
    player is within vision_range AND on the side it's currently facing."""

    def __init__(self, x):
        super().__init__(x, (200, 80, 70), facing=random.choice([-1, 1]))
        self.strength = random.uniform(MIN_STRENGTH, MAX_STRENGTH)
        self.parry_stun_duration = 1.2
        self.recruited = False
        self.order = "follow"
        self.guard_x = x
        self.patrol_direction = 1
        self.target = None
        self.selected = False
        self.original_color = self.color
        self.vision_range = 260
        self.alerted = False
        self.look_timer = random.uniform(1.0, 2.2)
        self.ai_state = "idle"
        self.ai_timer = random.uniform(0.5, 1.2)
        self.kill_rewarded = False
        self.investigate_x = None
        self.investigate_timer = 0.0
        self.fleeing = False
        self.flee_timer = 0.0
        self.flee_direction = 0
        self.flee_decided = False

    def alert_from_arrow(self, impact_x):
        self.alerted = True
        self.target = None
        self.investigate_x = impact_x
        self.investigate_timer = 2.2
        self.facing = -1 if impact_x < self.x else 1

    def maybe_start_flee(self, threat_x):
        if self.flee_decided or not self.alive or self.health > self.max_health * 0.3:
            return
        self.flee_decided = True
        if random.random() < 0.45:
            self.fleeing = True
            self.flee_timer = random.uniform(2.0, 3.5)
            self.flee_direction = 1 if self.x >= threat_x else -1

    def take_hit(self, attacker):
        outcome = super().take_hit(attacker)
        self.maybe_start_flee(attacker.x)
        return outcome

    def start_attack(self):
        was_attacking = self.attacking
        super().start_attack()
        if self.attacking and not was_attacking:
            self.attack_cooldown = 1.0

    def start_ai_attack(self):
        self.state = "run" if random.random() < 0.35 else "idle"
        self.start_attack()
        self.state = "idle"

    def ai_update(self, dt, player, fighters):
        if not self.alive:
            return
        if self.is_locked():
            self.vx, self.state = 0, "idle"
            return

        if self.fleeing:
            self.flee_timer -= dt
            if self.flee_timer <= 0:
                self.fleeing = False
                self.state, self.vx = "idle", 0
            else:
                self.facing = self.flee_direction
                self.state, self.vx = "run", self.facing * self.run_speed
                self.blocking = False
                self.x = max(30, min(WORLD_WIDTH - 30, self.x + self.vx * dt))
            return

        if not self.recruited and self.investigate_timer > 0:
            self.investigate_timer -= dt
            distance = self.investigate_x - self.x
            if abs(distance) > 24:
                self.facing = -1 if distance < 0 else 1
                self.state, self.vx = "walk", self.facing * self.walk_speed
                self.blocking = False
                self.x = max(30, min(WORLD_WIDTH - 30, self.x + self.vx * dt))
            else:
                self.state, self.vx, self.blocking = "idle", 0, False
            return

        if self.recruited:
            hostiles = [
                fighter for fighter in fighters
                if fighter is not self and fighter.alive and not fighter.recruited
            ]
            target = min(hostiles, key=lambda fighter: abs(fighter.x - self.x), default=None)
            target_dist = abs(target.x - self.x) if target else float("inf")
            can_engage = target and (
                self.order == "charge" or target_dist <= self.vision_range
            )
            if can_engage:
                self.facing = -1 if target.x < self.x else 1
                if target_dist <= 65:
                    self.state, self.vx, self.blocking = "idle", 0, False
                    self.start_ai_attack()
                else:
                    self.state = "run" if target_dist > 200 else "walk"
                    speed = self.run_speed if self.state == "run" else self.walk_speed
                    self.vx = self.facing * speed
                    self.blocking = False
                    self.x = max(30, min(WORLD_WIDTH - 30, self.x + self.vx * dt))
            elif self.order == "guard":
                patrol_limit = 55
                if abs(self.x - self.guard_x) >= patrol_limit:
                    self.patrol_direction = -1 if self.x > self.guard_x else 1
                self.facing = self.patrol_direction
                self.state, self.vx = "walk", self.patrol_direction * self.walk_speed * 0.45
                self.x = max(30, min(WORLD_WIDTH - 30, self.x + self.vx * dt))
                self.blocking = False
            else:
                self.facing = -1 if player.x < self.x else 1
                dist = abs(player.x - self.x)
                if dist > 100:
                    self.state = "run" if dist > 220 else "walk"
                    speed = self.run_speed if self.state == "run" else self.walk_speed
                    self.vx = self.facing * speed
                    self.blocking = False
                    self.x = max(30, min(WORLD_WIDTH - 30, self.x + self.vx * dt))
                else:
                    self.state, self.vx, self.blocking = "idle", 0, False
            return

        if not self.alerted:
            # patrol/idle: stand around, occasionally turn to "look" the other way
            self.look_timer -= dt
            if self.look_timer <= 0:
                self.facing *= -1
                self.look_timer = random.uniform(1.2, 2.4)
            self.state, self.vx, self.blocking = "idle", 0, False

            possible_targets = [player] + [
                fighter for fighter in fighters
                if fighter.recruited and fighter.alive
            ]
            visible_targets = [
                fighter for fighter in possible_targets
                if abs(fighter.x - self.x) <= self.vision_range
                and (self.facing == 1 and fighter.x >= self.x
                     or self.facing == -1 and fighter.x <= self.x)
            ]
            if visible_targets:
                self.target = min(visible_targets, key=lambda fighter: abs(fighter.x - self.x))
                self.alerted = True
            return

        # Once alerted, pursue the perceived target, which can be the player or a recruit.
        if self.target is None or not self.target.alive:
            self.target = player
        self.facing = -1 if self.target.x < self.x else 1
        dist = abs(self.target.x - self.x)

        self.ai_timer -= dt
        if self.ai_timer <= 0:
            if dist > 65:
                self.ai_state = "approach"
            else:
                self.ai_state = random.choice(["attack", "block", "attack", "idle"])
            self.ai_timer = random.uniform(0.5, 1.1)

        if self.ai_state == "approach" and dist > 65:
            self.state = "run" if dist > 200 else "walk"
            speed = self.run_speed if self.state == "run" else self.walk_speed
            self.vx = self.facing * speed
            self.x = max(30, min(WORLD_WIDTH - 30, self.x + self.vx * dt))
            self.blocking = False
        elif self.ai_state == "attack":
            self.state, self.vx, self.blocking = "idle", 0, False
            self.start_ai_attack()
        elif self.ai_state == "block":
            self.state, self.vx = "idle", 0
            self.try_block(True, random.random() < 0.2)
        else:
            self.state, self.vx, self.blocking = "idle", 0, False

    def draw(self, surf, camera_x):
        old_color = self.color
        if self.recruited:
            self.color = (70, 180, 105)
        super().draw(surf, camera_x)
        self.color = old_color
        if not self.alive:
            return
        r = self.rect.move(-int(camera_x), 0)
        if self.selected:
            pygame.draw.circle(surf, GOLD, (r.centerx, r.top - 28), 5, 2)
        bar_w, bar_h = 36, 5
        bx, by = r.centerx - bar_w // 2, r.top - 30
        pygame.draw.rect(surf, DARK_GRAY, (bx, by, bar_w, bar_h))
        pct = max(0, self.health / self.max_health)
        col = (220, 90, 70) if pct > 0.3 else (255, 60, 40)
        pygame.draw.rect(surf, col, (bx, by, int(bar_w * pct), bar_h))
        if self.recruited:
            pygame.draw.circle(surf, (80, 255, 130), (r.centerx, by - 8), 3)
        elif self.alerted:
            pygame.draw.circle(surf, (255, 50, 50), (r.centerx, by - 8), 3)

    def draw_vision(self, overlay, camera_x):
        """Draws this enemy's vision cone onto a shared translucent overlay."""
        if self.recruited or not self.alive:
            return
        r = self.rect.move(-int(camera_x), 0)
        cone_len, half_h = self.vision_range, 60
        apex = (r.centerx, r.centery)
        if self.facing == 1:
            p2, p3 = (apex[0] + cone_len, apex[1] - half_h), (apex[0] + cone_len, apex[1] + half_h)
        else:
            p2, p3 = (apex[0] - cone_len, apex[1] - half_h), (apex[0] - cone_len, apex[1] + half_h)
        color = (255, 70, 60, 55) if self.alerted else (210, 210, 90, 40)
        pygame.draw.polygon(overlay, color, [apex, p2, p3])


# ------------------------------------------------------------- World bits --
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

    def take_damage(self, dmg):
        if self.built:
            self.durability -= dmg
            if self.durability <= 0:
                self.built, self.durability = False, 0

    def draw(self, surf, camera_x):
        r = self.rect.move(-int(camera_x), 0)
        if self.built:
            pct = self.durability / self.max_durability
            if self.door_state == "open":
                pygame.draw.rect(surf, (90, 70, 50), r, 2, border_radius=3)
                pygame.draw.line(surf, (140, 100, 60), r.midtop, r.midbottom, 4)
            else:
                pygame.draw.rect(surf, (140 + int(60 * pct), 90, 60), r, border_radius=3)
            bar = pygame.Rect(r.x, r.y - 10, r.w, 5)
            pygame.draw.rect(surf, DARK_GRAY, bar)
            pygame.draw.rect(surf, GOLD, (bar.x, bar.y, int(bar.w * pct), bar.h))
        else:
            pygame.draw.rect(surf, (90, 70, 50), r, 2, border_radius=3)


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
        r = self.rect.move(-int(camera_x), 0)
        pygame.draw.rect(surf, (90, 60, 35), r)
        for i in range(6):
            hx = r.x + (i + 0.5) * r.w / 6
            height = 4 + self.stage * 6
            color = WHEAT_COLOR if self.stage == self.STAGES - 1 else (110, 140, 60)
            pygame.draw.line(surf, color, (hx, r.y), (hx, r.y - height), 3)


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
            self.price = max(2.0, self.price * 0.92)  # price sags as supply grows
        return round(total)

    def draw(self, surf, camera_x):
        r = self.rect.move(-int(camera_x), 0)
        pygame.draw.rect(surf, (150, 120, 70), r)
        pygame.draw.polygon(surf, (110, 80, 50), [(r.x - 6, r.y), (r.centerx, r.y - 22), (r.right + 6, r.y)])


class Tent:
    def __init__(self, x):
        self.x, self.w, self.h = x, 70, 55

    @property
    def rect(self):
        gy = ground_y(self.x)
        return pygame.Rect(int(self.x - self.w / 2), int(gy - self.h), self.w, self.h)

    def draw(self, surf, camera_x):
        r = self.rect.move(-int(camera_x), 0)
        pygame.draw.polygon(surf, (150, 60, 50), [(r.x, r.bottom), (r.centerx, r.top), (r.right, r.bottom)])
        pygame.draw.polygon(
            surf, (100, 40, 35),
            [(r.centerx - 14, r.bottom), (r.centerx, r.top + 16), (r.centerx + 14, r.bottom)],
        )


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
        r = self.rect.move(-int(camera_x), 0)
        pygame.draw.rect(surf, (116, 78, 48), r)
        pygame.draw.polygon(
            surf, (75, 45, 35),
            [(r.x - 10, r.y), (r.centerx, r.y - 38), (r.right + 10, r.y)],
        )
        pygame.draw.rect(surf, (45, 30, 25), (r.centerx - 12, r.bottom - 35, 24, 35))
        pygame.draw.rect(surf, (190, 155, 75), (r.x + 14, r.y + 26, 18, 18))
        pygame.draw.rect(surf, (190, 155, 75), (r.right - 32, r.y + 26, 18, 18))

    def draw_interior(self, surf):
        surf.fill((43, 34, 32))
        pygame.draw.rect(surf, (117, 82, 55), (70, 110, WIDTH - 140, HEIGHT - 160))
        pygame.draw.rect(surf, (78, 54, 42), (70, 110, WIDTH - 140, 12))
        pygame.draw.rect(surf, (56, 40, 34), (70, GROUND_BASE, WIDTH - 140, 12))

        # Door, bed, table, and storage are fixed interior interaction anchors.
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
        r = self.rect.move(-int(camera_x), 0)
        pygame.draw.line(surf, (88, 55, 32), (r.centerx, r.bottom), (r.centerx, r.top), 6)
        pygame.draw.circle(surf, GOLD if tethered else (145, 105, 65), (r.centerx, r.top), 7, 2)


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
        r = self.rect.move(-int(camera_x), 0)
        leg_sway = int(math.sin(self.animation_time * 5) * 2)
        body = pygame.Rect(r.x + 8, r.y + 16, 52, 28)
        pygame.draw.ellipse(surf, (112, 70, 42), body)
        neck = [(r.x + 48, r.y + 23), (r.x + 58, r.y - 6), (r.x + 70, r.y - 2), (r.x + 60, r.y + 27)]
        pygame.draw.polygon(surf, (112, 70, 42), neck)
        pygame.draw.circle(surf, (112, 70, 42), (r.x + 69, r.y - 4), 9)
        pygame.draw.circle(surf, (20, 20, 20), (r.x + 72, r.y - 6), 2)
        pygame.draw.line(surf, (72, 45, 30), (r.x + 18, r.bottom - 8), (r.x + 14, r.bottom + leg_sway), 6)
        pygame.draw.line(surf, (72, 45, 30), (r.x + 50, r.bottom - 8), (r.x + 54, r.bottom - leg_sway), 6)
        if self.mounted:
            pygame.draw.rect(surf, (120, 35, 30), (r.centerx - 18, r.y + 10, 36, 8))


# The world-object implementations live in the ordered package module.  This
# compatibility import keeps the current file runnable while the remaining
# actor and game orchestration sections are extracted.
from warlord.world_objects import FarmPatch, Horse as WorldHorse, House, LeashPost, Market, Tent, Wall


# ------------------------------------------------------------------- Game --
class Game:
    def __init__(self):
        self.state = MENU
        self.message, self.message_timer = "", 0
        self.prev_block_key = False
        self.selected_recruit = None
        self.layout = WorldLayout()
        self.reset_world()

    def reset_world(self):
        anchors = self.layout.anchors
        self.player = Player(anchors["camp"])
        self.enemies = [Enemy(anchors["frontier"] - 80)]
        self.wall = Wall(anchors["gate"])
        self.farm = FarmPatch(anchors["farm"])
        self.market = Market(anchors["market"])
        self.tent = Tent(anchors["tent"])
        self.horse = WorldHorse(anchors["camp"] + 75)
        self.leash_post = LeashPost(anchors["camp"] + 130)
        self.houses = [House(1030, "Village House"), House(1360, "Waystation")]
        self.current_house = None
        self.return_x = self.player.x
        self.arrows = []
        self.camera_x = 0
        self.selected_recruit = None

    def set_message(self, text, t=1.6):
        self.message, self.message_timer = text, t

    def enter_house(self, house):
        self.current_house = house
        self.return_x = self.player.x
        self.player.x = 500
        self.player.vx = 0
        self.player.state = "idle"
        self.player.floor_y = GROUND_BASE
        self.player.z = 0.0
        self.player.vz = 0.0
        self.player.on_ground = True
        self.camera_x = 0
        self.state = INTERIOR

    def exit_house(self):
        self.player.x = self.return_x
        self.player.vx = 0
        self.player.state = "idle"
        self.player.floor_y = None
        self.player.z = 0.0
        self.player.vz = 0.0
        self.player.on_ground = True
        self.current_house = None
        self.state = PLAYING
        self.camera_x = max(0, min(WORLD_WIDTH - WIDTH, self.player.x - WIDTH / 2))

    def update_interior(self, dt, keys, events):
        p = self.player
        p.update_death(dt)
        bow_key = keys[pygame.K_q]
        aim_delta = (1 if keys[pygame.K_w] else 0) - (1 if keys[pygame.K_s] else 0)
        arrow = p.update_bow(bow_key, dt, aim_delta)
        if arrow is not None:
            arrow.floor_y = GROUND_BASE
            arrow.world_y = GROUND_BASE - arrow.z
            self.arrows.append(arrow)
            self.set_message(f"Arrow fired ({arrow.damage} damage)", 0.8)
        block_key = keys[pygame.K_k]
        just_block = block_key and not self.prev_block_key
        self.prev_block_key = block_key

        for event in events:
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_e) and abs(p.x - self.current_house.interior_points["door"]) < 65:
                    self.exit_house()
                    return
                if event.key == pygame.K_e:
                    points = self.current_house.interior_points
                    if abs(p.x - points["bed"]) < 100:
                        p.health, p.stamina = p.max_health, p.max_stamina
                        self.set_message("Rested in the house", 1.2)
                    elif abs(p.x - points["table"]) < 100:
                        self.set_message("The table is ready for crafting", 1.2)
                    elif abs(p.x - points["storage"]) < 100:
                        if p.wheat > 0:
                            p.stored_wheat += p.wheat
                            stored = p.wheat
                            p.wheat = 0
                            self.set_message(f"Stored {stored} wheat", 1.2)
                        elif p.stored_wheat > 0:
                            p.wheat = min(MAX_WHEAT, p.stored_wheat)
                            p.stored_wheat -= p.wheat
                            self.set_message(f"Retrieved {p.wheat} wheat", 1.2)
                        else:
                            self.set_message("Storage is empty", 1.2)

                elif event.key == pygame.K_j:
                    p.start_attack()
                elif event.key == pygame.K_SPACE:
                    p.jump_or_slide()

        p.handle_input(keys, dt)
        interior_left, interior_right = self.current_house.interior_bounds
        p.x = max(interior_left, min(interior_right, p.x))
        jump_height = max(0.0, p.z)
        if not p.on_ground or p.vz != 0:
            p.vz -= GRAVITY * dt
            jump_height += p.vz * dt
            if jump_height <= 0:
                jump_height = 0.0
                p.vz = 0.0
                p.on_ground = True
            else:
                p.on_ground = False
        p.z = jump_height
        p.animation_time += dt
        p.update_attack(dt)
        p.try_block(block_key, just_block)
        p.update_defense_timers(dt)
        p.regen(dt)
        for arrow in self.arrows:
            arrow.update(dt)
        self.arrows = [arrow for arrow in self.arrows if arrow.alive]
        if self.message_timer > 0:
            self.message_timer -= dt

    def resolve_world_movement(self, fighter, previous_x):
        if self.wall.is_solid and fighter.rect.colliderect(self.wall.rect):
            fighter.x = previous_x
            fighter.vx = 0
            fighter.state = "idle"

    def reward_player_kill(self, enemy):
        if enemy.recruited or enemy.kill_rewarded:
            return
        enemy.kill_rewarded = True
        self.player.strength = min(
            MAX_STRENGTH,
            self.player.strength + PLAYER_KILL_STRENGTH_GAIN,
        )
        self.set_message(f"Strength increased to {self.player.strength:.2f}x", 1.2)

    def toggle_mount(self):
        p = self.player
        if p.mounted:
            p.mounted = False
            p.mount = None
            self.horse.mounted = False
            self.horse.x = p.x + p.facing * 35
            self.set_message("Dismounted", 1.0)
            return
        if self.horse.tethered:
            self.set_message("Untether the horse first", 1.0)
            return
        if abs(p.x - self.horse.x) > 75:
            self.set_message("Stand near the horse to mount", 1.0)
            return
        p.mounted = True
        p.mount = self.horse
        self.horse.mounted = True
        p.x = self.horse.x
        self.set_message("Mounted horse", 1.0)

    def toggle_tether(self):
        if abs(self.player.x - self.leash_post.x) > 80:
            self.set_message("Stand near the leash post", 1.0)
            return
        if self.player.mounted:
            self.set_message("Dismount before tethering", 1.0)
            return
        self.horse.tethered = not self.horse.tethered
        self.horse.post_x = self.leash_post.x if self.horse.tethered else None
        self.set_message("Horse tethered" if self.horse.tethered else "Horse untethered", 1.0)

    def transfer_horse_inventory(self):
        if abs(self.player.x - self.horse.x) > 85:
            self.set_message("Stand near the horse", 1.0)
            return
        if self.player.wheat > 0:
            self.horse.inventory_wheat += self.player.wheat
            amount = self.player.wheat
            self.player.wheat = 0
            self.set_message(f"Stored {amount} wheat on horse", 1.0)
        elif self.horse.inventory_wheat > 0:
            amount = min(MAX_WHEAT, self.horse.inventory_wheat)
            self.player.wheat = amount
            self.horse.inventory_wheat -= amount
            self.set_message(f"Retrieved {amount} wheat from horse", 1.0)
        else:
            self.set_message("Horse inventory is empty", 1.0)

    def spawn_enemy(self):
        if len(self.enemies) >= MAX_ENEMIES:
            self.set_message("Max enemies reached")
            return
        offset = random.choice([-1, 1]) * random.randint(200, 420)
        x = max(60, min(WORLD_WIDTH - 60, self.player.x + offset))
        self.enemies.append(Enemy(x))
        self.set_message(f"Enemy spawned ({len(self.enemies)} active)")

    def recruit_enemy(self):
        candidates = [
            en for en in self.enemies
            if en.alive and not en.recruited
            and abs(en.x - self.player.x) < 85
        ]
        if not candidates:
            self.set_message("Stand near a weakened enemy to recruit it")
            return
        target = min(candidates, key=lambda en: abs(en.x - self.player.x))
        if target.health > target.max_health * 0.35:
            self.set_message("Weaken the enemy below 35% HP first")
            return
        if self.player.money < 10:
            self.set_message("Recruitment costs 10g")
            return
        self.player.money -= 10
        target.recruited = True
        target.alerted = False
        target.color = (70, 180, 105)
        self.selected_recruit = target
        target.selected = True
        target.head_bob_timer = 0.45
        self.set_message("Enemy recruited! It will follow you")

    def order_recruits(self, order):
        recruit = self.selected_recruit
        if recruit is None or not recruit.alive or not recruit.recruited:
            self.set_message("Press E near a recruit to select one")
            return
        recruit.order = order
        if order == "guard":
            recruit.guard_x = self.player.x
            recruit.patrol_direction = 1 if self.player.x >= recruit.x else -1
        elif order == "follow":
            recruit.target = None
        recruit.head_bob_timer = 0.6
        self.player.head_bob_timer = 0.45
        labels = {"guard": "guard this area", "follow": "follow", "charge": "charge"}
        self.set_message(f"Recruit ordered to {labels[order]}")

    def handle_interact(self):
        p = self.player
        if abs(p.x - self.leash_post.x) < 30:
            self.toggle_tether()
            return
        if abs(p.x - self.horse.x) < 45:
            self.toggle_mount()
            return
        nearby_recruits = [
            en for en in self.enemies
            if en.alive and en.recruited and abs(en.x - p.x) < 85
        ]
        if nearby_recruits:
            selected = min(nearby_recruits, key=lambda en: abs(en.x - p.x))
            if self.selected_recruit is not None:
                self.selected_recruit.selected = False
            self.selected_recruit = selected
            selected.selected = True
            selected.head_bob_timer = 0.45
            self.player.head_bob_timer = 0.35
            self.set_message("Recruit selected - press 1, 2, or 3 to give orders")
        elif self.houses and any(
            abs(house.x - p.x) < house.w / 2 + 45 for house in self.houses):
            nearby_house = min(self.houses, key=lambda house: abs(house.x - p.x))
            if abs(nearby_house.x - p.x) < nearby_house.w / 2 + 45:
                self.enter_house(nearby_house)
                self.set_message(f"Entered {nearby_house.name}")
                return
        elif abs(p.x - self.farm.x) < self.farm.w / 2 + 40:
            amt = self.farm.harvest()
            space = MAX_WHEAT - p.wheat
            added = min(amt, max(0, space))
            p.wheat += added
            if added:
                self.set_message(f"Harvested {added} wheat")
            elif amt and not space:
                self.set_message("Sack is full (10 wheat)")
            else:
                self.set_message("Wheat not ready yet")
        elif abs(p.x - self.market.x) < self.market.w / 2 + 40:
            if p.wheat > 0:
                sold = p.wheat
                earned = self.market.sell(sold)
                p.money += earned
                self.set_message(f"Sold {sold} wheat for {earned}g")
                p.wheat = 0
            else:
                self.set_message("No wheat to sell")
        elif abs(p.x - self.tent.x) < self.tent.w / 2 + 40:
            p.health, p.stamina = p.max_health, p.max_stamina
            self.set_message("Rested - HP/Stamina restored")
        elif abs(p.x - self.wall.x) < self.wall.w / 2 + 40:
            if not self.wall.built:
                if p.money >= 10:
                    p.money -= 10
                    self.wall.build()
                    self.set_message("Wall built (10g)")
                else:
                    self.set_message("Need 10g to build wall")
            else:
                door_state = self.wall.toggle_door()
                if door_state == "locked":
                    self.set_message("The gate is locked")
                else:
                    self.set_message(f"Gate {door_state}")

    def update(self, dt, keys, events):
        if self.state == MENU:
            for e in events:
                if e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.reset_world()
                    self.state = PLAYING
                if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                    pygame.quit()
                    sys.exit()
            return

        if self.state == INTERIOR:
            self.update_interior(dt, keys, events)
            return

        if self.state == GAMEOVER:
            for e in events:
                if e.type == pygame.KEYDOWN and e.key == pygame.K_RETURN:
                    self.state = MENU
            return

        p = self.player
        p.update_death(dt)
        bow_key = keys[pygame.K_q]
        aim_delta = (1 if keys[pygame.K_w] else 0) - (1 if keys[pygame.K_s] else 0)
        arrow = p.update_bow(bow_key, dt, aim_delta)
        if arrow is not None:
            self.arrows.append(arrow)
            self.set_message(f"Arrow fired ({arrow.damage} damage)", 0.8)
        block_key = keys[pygame.K_k]
        just_block = block_key and not self.prev_block_key
        self.prev_block_key = block_key

        previous_player_x = p.x
        p.handle_input(keys, dt)
        self.resolve_world_movement(p, previous_player_x)
        p.update_physics(dt)
        p.update_attack(dt)
        p.try_block(block_key, just_block)
        p.update_defense_timers(dt)
        p.regen(dt)

        for e in events:
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_j:
                    p.start_attack()
                elif e.key == pygame.K_SPACE:
                    p.jump_or_slide()
                elif e.key == pygame.K_e:
                    self.handle_interact()
                elif e.key == pygame.K_r:
                    self.recruit_enemy()
                elif e.key == pygame.K_1:
                    self.order_recruits("guard")
                elif e.key == pygame.K_2:
                    self.order_recruits("follow")
                elif e.key == pygame.K_3:
                    self.order_recruits("charge")
                elif e.key == pygame.K_n:
                    self.spawn_enemy()
                elif e.key == pygame.K_h:
                    self.transfer_horse_inventory()
                elif e.key == pygame.K_ESCAPE:
                    self.state = MENU

        self.horse.update(dt, p)
        for en in self.enemies:
            in_tent = en.recruited and abs(en.x - self.tent.x) <= self.tent.w / 2 + 35
            previous_enemy_x = en.x
            en.ai_update(dt, p, self.enemies)
            self.resolve_world_movement(en, previous_enemy_x)
            en.update_death(dt)
            en.update_physics(dt)
            en.update_attack(dt)
            en.update_defense_timers(dt)
            en.regen(dt)
            if in_tent:
                en.health = min(en.max_health, en.health + 12 * dt)

        for arrow in self.arrows:
            arrow.update(dt)
            if not arrow.alive:
                continue
            if arrow.stuck:
                continue
            for en in self.enemies:
                if (en.alive and not en.recruited and arrow.owner is p
                        and arrow.rect.colliderect(en.rect)):
                    en.health -= arrow.damage
                    en.alert_from_arrow(arrow.origin_x)
                    if en.health <= 0:
                        en.die()
                    else:
                        en.maybe_start_flee(arrow.origin_x)
                    arrow.stick_to(en)
                    self.set_message(f"Arrow hit for {arrow.damage}", 0.8)
                    if not en.alive:
                        self.reward_player_kill(en)
                    break
            if arrow.alive and self.wall.is_solid and arrow.rect.colliderect(self.wall.rect):
                self.wall.take_damage(arrow.damage)
                arrow.stick_to()
                self.set_message("Arrow struck the wall", 0.8)
        self.arrows = [arrow for arrow in self.arrows if arrow.alive]

        # player's swing vs enemies / wall (one target per swing)
        if p.attacking and not p.has_hit and p.attack_in_windup():
            for en in self.enemies:
                if (en.alive and en.parry_window > 0
                        and abs(en.x - p.x) <= 65):
                    outcome = en.take_hit(p)
                    self.set_message(f"Your attack: {outcome}!", 1.0)
                    if not en.alive:
                        self.reward_player_kill(en)
                    p.has_hit = True
                    break

        if p.attacking and not p.has_hit and p.hitbox:
            hit_something = False
            for en in self.enemies:
                if en.alive and not en.recruited and p.hitbox.colliderect(en.rect):
                    outcome = en.take_hit(p)
                    self.set_message(f"Your attack: {outcome}!", 1.0)
                    if not en.alive:
                        self.reward_player_kill(en)
                    hit_something = True
                    break
            if not hit_something and self.wall.is_solid and p.hitbox.colliderect(self.wall.rect):
                self.wall.take_damage(p.damage_of_current_attack())
                hit_something = True
            if hit_something:
                p.has_hit = True

        # hostile swings can hit the player or any recruited fighter
        for en in self.enemies:
            if en.attacking and not en.recruited and not en.has_hit:
                targets = [p] + [ally for ally in self.enemies if ally.alive and ally.recruited]
                for target in targets:
                    if not target.alive:
                        continue
                    if (target.parry_window > 0 and en.attack_in_windup()
                            and abs(target.x - en.x) <= 65):
                        outcome = target.take_hit(en)
                        en.has_hit = True
                        label = "Recruit" if target is not p else "Enemy"
                        self.set_message(f"{label} attack: {outcome}!", 1.0)
                        break
                if en.has_hit or not en.hitbox:
                    continue
                for target in targets:
                    if not target.alive:
                        continue
                    wall_between = (
                        self.wall.is_solid
                        and self.wall.rect.colliderect(en.hitbox)
                        and min(target.x, en.x) < self.wall.rect.centerx < max(target.x, en.x)
                    )
                    if wall_between:
                        self.wall.take_damage(en.damage_of_current_attack() * 0.5)
                        en.has_hit = True
                        break
                    if en.hitbox.colliderect(target.rect):
                        outcome = target.take_hit(en)
                        en.has_hit = True
                        label = "Recruit" if target is not p else "Enemy"
                        self.set_message(f"{label} attack: {outcome}!", 1.0)
                        break

        # recruited fighters use the same attack rules against hostile enemies
        for ally in self.enemies:
            if ally.recruited and ally.attacking and not ally.has_hit:
                for hostile in self.enemies:
                    if (hostile.alive and not hostile.recruited
                            and hostile.parry_window > 0
                            and ally.attack_in_windup()
                            and abs(hostile.x - ally.x) <= 65):
                        outcome = hostile.take_hit(ally)
                        ally.has_hit = True
                        self.set_message(f"Ally attack: {outcome}!", 1.0)
                        break
                    if (hostile.alive and not hostile.recruited and ally.hitbox
                            and ally.hitbox.colliderect(hostile.rect)):
                        outcome = hostile.take_hit(ally)
                        ally.has_hit = True
                        self.set_message(f"Ally attack: {outcome}!", 1.0)
                        break

        self.farm.update(dt)
        self.market.update(dt)

        expired_enemies = [en for en in self.enemies if not en.alive and en.death_timer <= 0]
        if expired_enemies:
            remaining = [en for en in self.enemies if en.alive or en.death_timer > 0]
            self.enemies = remaining
            living_hostiles = sum(en.alive and not en.recruited for en in remaining)
            self.set_message(f"Enemy defeated! ({living_hostiles} hostile remaining)")

        self.camera_x = max(0, min(WORLD_WIDTH - WIDTH, p.x - WIDTH / 2))

        if self.message_timer > 0:
            self.message_timer -= dt
        if not p.alive and p.death_timer <= 0:
            self.state = GAMEOVER

    # --------------------------------------------------------------- draw --
    def draw(self, surf):
        surf.fill(SKY)
        if self.state == INTERIOR:
            self.current_house.draw_interior(surf)
            self.player.draw(surf, 0)
            for arrow in self.arrows:
                arrow.draw(surf, 0)
            surf.blit(font_small.render("A/D move   E interact   E at the door exits", True, WHITE), (20, HEIGHT - 28))
            if self.message_timer > 0:
                mt = font_med.render(self.message, True, (255, 255, 200))
                surf.blit(mt, mt.get_rect(center=(WIDTH // 2, 70)))
            return
        self.layout.draw_background(surf, self.camera_x)
        self.draw_ground(surf, self.camera_x)

        if self.state == MENU:
            self.draw_menu(surf)
            return
        if self.state == GAMEOVER:
            self.draw_gameover(surf)
            return

        cam = self.camera_x
        self.farm.draw(surf, cam)
        self.market.draw(surf, cam)
        self.tent.draw(surf, cam)
        self.wall.draw(surf, cam)
        self.leash_post.draw(surf, cam, self.horse.tethered)
        self.horse.draw(surf, cam)
        for house in self.houses:
            house.draw(surf, cam)

        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        for en in self.enemies:
            en.draw_vision(overlay, cam)
        surf.blit(overlay, (0, 0))

        self.player.draw(surf, cam)
        for en in self.enemies:
            en.draw(surf, cam)
        for arrow in self.arrows:
            arrow.draw(surf, cam)

        self.draw_hud(surf)

    def draw_ground(self, surf, cam):
        step = 10
        pts = [(0, HEIGHT)]
        for sx in range(0, WIDTH + step, step):
            pts.append((sx, ground_y(cam + sx)))
        pts.append((WIDTH, HEIGHT))
        pygame.draw.polygon(surf, (35, 50, 35), pts)
        pygame.draw.lines(surf, (20, 30, 20), False, pts[1:-1], 3)

    def draw_menu(self, surf):
        title = font_big.render("WARLORD 2D", True, WHITE)
        surf.blit(title, title.get_rect(center=(WIDTH // 2, 150)))
        for i, o in enumerate(["Start Campaign", "Continue Campaign", "Quick Battle", "Settings", "Quit"]):
            t = font_med.render(o, True, WHITE if i == 0 else GRAY)
            surf.blit(t, t.get_rect(center=(WIDTH // 2, 250 + i * 40)))
        hint = font_small.render("ENTER/SPACE = Start Campaign    ESC = Quit", True, GRAY)
        surf.blit(hint, hint.get_rect(center=(WIDTH // 2, HEIGHT - 40)))

    def draw_gameover(self, surf):
        t = font_big.render("YOU DIED", True, RED)
        surf.blit(t, t.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 20)))
        h = font_small.render("Press ENTER to return to menu", True, WHITE)
        surf.blit(h, h.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 30)))

    def draw_bar(self, surf, x, y, w, h, pct, fg, bg=DARK_GRAY):
        pygame.draw.rect(surf, bg, (x, y, w, h))
        pygame.draw.rect(surf, fg, (x, y, int(w * max(0, pct)), h))
        pygame.draw.rect(surf, BLACK, (x, y, w, h), 1)

    def draw_hud(self, surf):
        p = self.player
        self.draw_bar(surf, 20, 16, 180, 16, p.health / p.max_health, RED)
        self.draw_bar(surf, 20, 36, 180, 10, p.stamina / p.max_stamina, (90, 200, 90))
        surf.blit(font_small.render(f"Wheat: {p.wheat}   Gold: {p.money}", True, WHITE), (20, 52))
        hostile_count = sum(not en.recruited for en in self.enemies)
        ally_count = sum(en.recruited for en in self.enemies)
        surf.blit(font_small.render(f"Hostiles: {hostile_count}   Allies: {ally_count}", True, WHITE), (20, 72))
        if p.bow_charge > 0:
            self.draw_bar(surf, 220, 16, 150, 16, p.bow_charge / MAX_BOW_CHARGE, (220, 170, 65))
            surf.blit(font_small.render("BOW", True, WHITE), (378, 16))
        selected_text = "Selected: none"
        if self.selected_recruit is not None and self.selected_recruit.alive:
            selected_text = f"Selected recruit: {self.selected_recruit.order}"
        surf.blit(font_small.render(selected_text, True, GOLD), (20, 90))
        surf.blit(font_small.render(f"Strength: {p.strength:.1f}x", True, WHITE), (20, 108))

        surf.blit(font_small.render(f"Wheat price: {self.market.price:.1f}g", True, GOLD), (WIDTH // 2 - 60, 16))

        controls = "A/D move|Shift run|W/S aim bow|Space jump/slide|J attack|Q bow|K block/parry|E mount/interact|H horse storage|R recruit|1 guard|2 follow|3 charge|N spawn"
        surf.blit(font_small.render(controls, True, (170, 170, 170)), (14, HEIGHT - 24))

        if self.message_timer > 0:
            mt = font_med.render(self.message, True, (255, 255, 200))
            surf.blit(mt, mt.get_rect(center=(WIDTH // 2, 90)))


def main():
    game = Game()
    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0
        events = pygame.event.get()
        for e in events:
            if e.type == pygame.QUIT:
                running = False
        keys = pygame.key.get_pressed()
        game.update(dt, keys, events)
        game.draw(screen)
        pygame.display.flip()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()