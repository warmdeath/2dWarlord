"""Humanoid: a Body with a skeleton, equipment and combat state.

Controllers (keyboard, NPC brain, formation) only ever fill in an Intent; the humanoid turns intents
into movement/actions the same way for everyone. That is what lets a peasant, a knight, or you
use the exact same fighting rules.
"""
import math

from ..settings import (TILE, WALK_SPEED, RUN_SPEED, CROUCH_SPEED, SWIM_SPEED, JUMP_SPEED, CLIMB_SPEED)
from ..combat.weapons import WEAPONS, SHIELDS, ARMORS, HELMETS
from ..gfx.rig import compute_pose
from .body import Body

PARRY_WINDOW = 0.18
STAND_H, CROUCH_H = 42, 28


class Intent:
    __slots__ = ("mx", "run", "crouch", "jump", "jump_held", "up", "down", "attack", "attack_held", "block",
                 "aim", "use", "release")

    def __init__(self):
        self.clear()

    def clear(self):
        self.mx = 0.0
        self.run = False
        self.crouch = False
        self.jump = False
        self.jump_held = False
        self.up = False
        self.down = False
        self.attack = False
        self.attack_held = False
        self.block = False
        self.aim = 0.0
        self.use = False
        self.release = False


class Humanoid(Body):
    w = 14
    h = STAND_H
    kind = "human"

    def __init__(self, x, y, look, faction="none", name="Unbekannt", rank=0):
        super().__init__(x, y)
        self.look = look
        self.faction = faction
        self.name = name
        self.rank = rank
        self.intent = Intent()
        self.state = "idle"
        self.anim_t = 0.0
        self.walk_phase = 0.0
        self.action = None
        self.combo = 0
        self.combo_window = 0.0
        self.queued_attack = False
        self.blocking = False
        self.block_t = 0.0
        self.riposte_ready = 0.0
        self.stagger = 0.0
        self.hurt_flash = 0.0
        self.invuln = 0.0
        self.max_hp = 100.0
        self.hp = 100.0
        self.stamina = 100.0
        self.max_stamina = 100.0
        self.posture = 100.0
        self.breath = 12.0
        self.strength = 1.0
        self.skill = 0.5
        self.dead = False
        self.dead_t = 0.0
        self.weapon_key = "fists"
        self.weapon_def = WEAPONS["fists"]
        self.weapon_drawn = False
        self.shield = None
        self.armor = ARMORS["kleidung"]
        self.helmet = None
        self.mount = None
        self.slide_t = 0.0
        self.hit_ids = set()
        self.last_attacker = None
        self.reload = 0.0
        self.bow_draw = 0.0
        self.ammo = 30
        self.formation = None
        self.formation_stance = None
        self.aware = 0.0               # >0 while alert (no backstabs)
        self.bubble = None             # speech bubble (text, timer, gloss)
        self.pose = compute_pose(self)
        self.drowning_tick = 0.0
        self.coyote = 0.0
        self.jump_buffer = 0.0
        self.carry_light = 0.0
        self.kills = 0
        self.morale = 1.0

    # ---------------------------------------------------------------- equipment
    def equip(self, weapon=None, shield=None, armor=None, helmet=None):
        if weapon is not None:
            self.weapon_key = weapon if weapon in WEAPONS else "fists"
            self.weapon_def = WEAPONS[self.weapon_key]
            if self.weapon_def.two_handed:
                self.shield = None
        if shield is not None:
            self.shield = SHIELDS.get(shield) if shield else None
            if self.shield and self.weapon_def.two_handed:
                self.shield = None
        if armor is not None:
            self.armor = ARMORS.get(armor, ARMORS["kleidung"])
        if helmet is not None:
            self.helmet = helmet or None
        self.weight = 1.0 + self.armor.weight * 1.4 + (self.shield.weight if self.shield else 0) + (
            0.08 if self.helmet else 0)

    @property
    def armor_value(self):
        return self.armor

    def speed_mult(self):
        return 1.0 - self.armor.weight * 0.45 - (0.05 if self.shield and self.shield.style == "pavise" else 0)

    # ---------------------------------------------------------------- combat hooks
    def can_act(self):
        return not self.dead and self.stagger <= 0 and self.mount is None or (self.mount is not None and not self.dead)

    def start_attack(self, game):
        if self.dead or self.stagger > 0:
            return
        wd = self.weapon_def
        if wd.kind in ("bow", "crossbow"):
            return
        if self.action is not None and self.action["kind"] == "attack":
            self.queued_attack = True
            return
        if self.stamina < 6:
            return
        self.weapon_drawn = True
        mv = None
        moves = wd.moves
        if self.riposte_ready > 0 and (self.state == "crouch" or self.intent.crouch):
            mv = moves["riposte"]
            self.riposte_ready = 0
            game.fx.text(self.cx, self.y - 10, "Konter!", (255, 220, 120), gloss="counter")
        elif self.mount is not None:
            mv = moves["run"]
        elif not self.on_ground and self.in_water < 0.3 and not self.climbing:
            mv = moves["air"]
        elif self.state == "run" or (abs(self.vx) > RUN_SPEED * 0.8 and self.on_ground):
            mv = moves["run"]
        elif self.state in ("crouch", "sneak") or self.intent.crouch:
            mv = moves["crouch"]
        else:
            if self.combo_window <= 0:
                self.combo = 0
            mv = moves["combo"][self.combo % 3]
            self.combo += 1
        self.action = {"kind": "attack", "move": mv, "t": 0.0, "lunged": False}
        self.hit_ids = set()
        self.stamina -= wd.stamina * mv.stamina * (0.6 if self.mount else 1.0)
        self.blocking = False

    def take_hit(self, game, attacker, dmg, dtype, posture, flags=(), high=True, source_x=None, arrow=False):
        """Returns 'parry', 'block', 'hit' or 'immune'."""
        if self.dead or self.invuln > 0:
            return "immune"
        sx = source_x if source_x is not None else (attacker.cx if attacker else self.cx)
        facing_source = (sx - self.cx) * self.facing > 0
        if attacker is not None:
            self.last_attacker = attacker
        self.aware = 4.0
        if self.blocking and facing_source and not ("unblockable" in flags):
            if not arrow and self.block_t < PARRY_WINDOW and attacker is not None:
                attacker.stagger = max(attacker.stagger, 0.75)
                attacker.posture -= 35
                attacker.action = None
                self.riposte_ready = 0.9
                self.posture = min(100, self.posture + 10)
                game.fx.sparks(self.cx + self.facing * 10, self.y + 14, 14)
                game.fx.text(self.cx, self.y - 12, "Parade!", (255, 240, 160), gloss="parry")
                game.sfx("parry")
                return "parry"
            eff = self.shield.block if self.shield else self.weapon_def.block
            if arrow and self.shield:
                eff = 1.0
            if "wrap" in flags and self.shield:
                eff *= 0.5
            pmult = 2.6 if ("shieldbreak" in flags and self.shield) else 1.0
            self.stamina -= dmg * 0.6 * (0.5 if self.shield else 1.0)
            self.posture -= posture * pmult
            dmg *= (1.0 - eff)
            game.fx.sparks(self.cx + self.facing * 8, self.y + 14, 6)
            game.sfx("block")
            if self.posture <= 0 or self.stamina <= 0:
                self.stagger = 1.1
                self.blocking = False
                self.posture = 40
                game.fx.text(self.cx, self.y - 12, "Deckung gebrochen!", (255, 120, 90), gloss="guard broken")
            if dmg < 0.5:
                return "block"
            result = "block"
        else:
            result = "hit"
        # armour
        a = self.armor
        red = {"cut": a.cut, "pierce": a.pierce, "blunt": a.blunt}.get(dtype, 0.0)
        if high and self.helmet:
            red += HELMETS[self.helmet][0]
        if "armorbreak" in flags:
            red *= 0.4
        if "armorpierce" in flags:
            red *= 0.5
        dmg *= (1.0 - min(0.9, red))
        if "backstab" in flags and not facing_source and self.aware <= 4.0 and getattr(self, "unaware", False):
            dmg *= 3
            game.fx.text(self.cx, self.y - 22, "Meuchelstoß!", (230, 60, 60), gloss="assassination")
        self.hp -= dmg
        self.hurt_flash = 0.15
        self.posture -= posture * 0.5
        kb = 60 + dmg * 5
        d = 1 if self.cx >= sx else -1
        self.vx += d * kb
        if self.on_ground and dmg > 8:
            self.vy = min(self.vy, -90)
        if dmg > 14 and self.stagger <= 0:
            self.stagger = 0.25
            self.action = None
        if self.posture <= 0:
            self.stagger = 0.9
            self.posture = 50
        game.fx.blood(self.cx, self.y + 16, int(4 + dmg * 0.5), d)
        game.fx.number(self.cx, self.y - 4, int(dmg))
        game.sfx("hit")
        if self.mount is not None and "hook" in flags:
            game.dismount(self, thrown=True)
            game.fx.text(self.cx, self.y - 24, "Vom Pferd gerissen!", (255, 200, 120), gloss="pulled off the horse")
        if self.hp <= 0:
            self.die(game, attacker)
        return result

    def die(self, game, killer=None):
        if self.dead:
            return
        self.dead = True
        self.hp = 0
        self.state = "dead"
        self.action = None
        self.blocking = False
        if self.mount is not None:
            game.dismount(self)
        if killer is not None:
            killer.kills += 1
        game.on_death(self, killer)

    # ---------------------------------------------------------------- main update
    def update(self, game, dt):
        world = game.world
        self.anim_t += dt
        it = self.intent
        for attr in ("stagger", "hurt_flash", "invuln", "combo_window", "riposte_ready", "aware", "coyote",
                     "jump_buffer"):
            v = getattr(self, attr)
            if v > 0:
                setattr(self, attr, max(0.0, v - dt))
        if self.bubble:
            self.bubble[1] -= dt
            if self.bubble[1] <= 0:
                self.bubble = None
        if self.dead:
            self.dead_t += dt
            self.vx *= 0.9
            self.physics(world, dt)
            self.pose = compute_pose(self)
            return
        if self.mount is not None:
            self._update_mounted(game, dt)
            return
        # regen
        if self.action is None and not self.blocking:
            self.stamina = min(self.max_stamina, self.stamina + 22 * dt)
        self.posture = min(100.0, self.posture + 14 * dt)
        # --- blocking
        want_block = it.block and self.stagger <= 0 and self.weapon_def.kind not in ("bow", "crossbow")
        if want_block and not self.blocking and (self.action is None or self.action["kind"] != "attack"):
            self.blocking = True
            self.block_t = 0.0
            self.weapon_drawn = True
            self.action = {"kind": "block"}
        elif not want_block and self.blocking:
            self.blocking = False
            if self.action and self.action["kind"] == "block":
                self.action = None
        if self.blocking:
            self.block_t += dt
            self.stamina -= 2 * dt
        # --- crouch / hitbox height
        want_crouch = it.crouch and self.in_water < 0.3 and not self.climbing
        if want_crouch and self.h != CROUCH_H and self.on_ground:
            self.y += STAND_H - CROUCH_H
            self.h = CROUCH_H
        elif not want_crouch and self.h == CROUCH_H and self.slide_t <= 0:
            ny = self.y - (STAND_H - CROUCH_H)
            old_h = self.h
            self.h = STAND_H
            if self._box_hits(world, self.x, ny):
                self.h = old_h  # no headroom
            else:
                self.y = ny
        crouched = self.h == CROUCH_H
        # --- horizontal movement
        sp = WALK_SPEED
        if it.run and not crouched and self.stamina > 5:
            sp = RUN_SPEED
        if crouched:
            sp = CROUCH_SPEED
        if self.in_water > 0.4:
            sp = SWIM_SPEED
        if self.blocking:
            sp = min(sp, WALK_SPEED * 0.55)
        if self.action is not None and self.action["kind"] == "attack":
            sp *= 0.25
        if self.action is not None and self.action["kind"] in ("bow", "crossbow"):
            sp *= 0.5
        sp *= self.speed_mult() * (0.0 if self.stagger > 0 else 1.0)
        if self.slide_t > 0:
            self.slide_t -= dt
            self.vx *= (1 - 1.2 * dt)
            if self.slide_t <= 0 or abs(self.vx) < 30:
                self.slide_t = 0
        else:
            target = it.mx * sp
            accel = 1400 if self.on_ground else 700
            if self.in_water > 0.3:
                accel = 500
            if abs(target - self.vx) < accel * dt:
                self.vx = target
            else:
                self.vx += math.copysign(accel * dt, target - self.vx)
            if it.mx != 0 and not self.blocking and (self.action is None or self.action["kind"] in ("work",)):
                self.facing = 1 if it.mx > 0 else -1
            elif it.mx != 0 and self.action and self.action["kind"] in ("bow", "crossbow"):
                pass
        if it.run and abs(self.vx) > WALK_SPEED and self.on_ground:
            self.stamina -= 9 * dt
        # --- slide: crouch while running
        if (it.crouch and abs(self.vx) > RUN_SPEED * 0.85 and self.on_ground and self.slide_t <= 0
                and self.stamina > 10):
            self.slide_t = 0.55
            self.vx = math.copysign(RUN_SPEED * 1.6, self.vx)
            self.stamina -= 12
            self.invuln = 0.25
        # --- ladders / swimming / jumping
        if self.on_ladder and (it.up or it.down) and not crouched:
            self.climbing = True
        if self.climbing:
            if not self.on_ladder:
                self.climbing = False
            else:
                self.vy = -CLIMB_SPEED if it.up else CLIMB_SPEED if it.down else 0.0
                self.vx *= 0.5
                self.walk_phase += abs(self.vy) * dt * 0.12
                if it.jump:
                    self.climbing = False
                    self.vy = -JUMP_SPEED * 0.6
        if self.on_ground:
            self.coyote = 0.1
        if it.jump:
            self.jump_buffer = 0.12
        if self.in_water > 0.35:
            if it.jump_held or it.up:
                self.vy -= 900 * dt * (1.0 if self.weight < 1.3 else 0.65)
                self.vy = max(self.vy, -170)
            if it.down:
                self.vy += 400 * dt
            if self.in_water < 0.7 and it.jump and self.vy > -50:
                self.vy = -JUMP_SPEED * 0.75   # leap out of the water
        elif self.jump_buffer > 0 and self.coyote > 0 and not crouched and self.stagger <= 0:
            self.vy = -JUMP_SPEED * (0.9 if self.weight > 1.3 else 1.0)
            self.on_ground = False
            self.coyote = 0
            self.jump_buffer = 0
        if it.down and it.jump and self.on_ground:
            self.drop_through = 0.25
        if not it.jump_held and self.vy < -150 and self.in_water < 0.3 and not self.climbing:
            self.vy += 1600 * dt   # variable jump height
        # --- attacks
        wd = self.weapon_def
        if wd.kind == "bow":
            self._update_bow(game, dt)
        elif wd.kind == "crossbow":
            self._update_crossbow(game, dt)
        elif it.attack:
            self.start_attack(game)
        if self.action is not None and self.action["kind"] == "attack":
            self._advance_attack(game, dt)
        if self.action is not None and self.action["kind"] == "use":
            self.action["t"] += dt
            if self.action["t"] >= self.action["dur"]:
                self.action = None
        # physics
        self.physics(world, dt)
        self._environment(game, dt)
        self._classify(dt)
        self.pose = compute_pose(self)

    def _advance_attack(self, game, dt):
        a = self.action
        mv = a["move"]
        a["t"] += dt
        t = a["t"]
        if t >= mv.windup and not a["lunged"]:
            a["lunged"] = True
            if mv.lunge and self.on_ground:
                self.vx = self.facing * max(abs(self.vx), mv.lunge)
            if mv.arc == "plunge":
                self.vy = max(self.vy, 350)
            game.sfx("swing")
        if mv.windup <= t <= mv.windup + mv.active:
            game.combat.melee(self, mv)
        if t >= mv.windup + mv.active + mv.recover:
            self.action = None
            self.combo_window = 0.35
            if self.queued_attack:
                self.queued_attack = False
                self.start_attack(game)

    def _update_bow(self, game, dt):
        it = self.intent
        if self.reload > 0:
            self.reload -= dt
        if it.attack_held and self.reload <= 0 and self.ammo > 0 and self.stagger <= 0:
            if self.action is None or self.action["kind"] != "bow":
                self.action = {"kind": "bow", "draw": 0.0, "aim": it.aim}
            self.action["draw"] = min(1.0, self.action["draw"] + dt / 0.9)
            self.action["aim"] = it.aim
            self.stamina -= 4 * dt
        elif self.action is not None and self.action["kind"] == "bow":
            d = self.action["draw"]
            if d > 0.2:
                game.fire_arrow(self, self.action["aim"], d, kind="arrow")
                self.ammo -= 1
                self.reload = 0.35
            self.action = None

    def _update_crossbow(self, game, dt):
        it = self.intent
        if self.action is None or self.action["kind"] != "crossbow":
            self.action = {"kind": "crossbow", "aim": it.aim, "reload": 0.0, "loaded": True}
        a = self.action
        a["aim"] = it.aim
        if a["reload"] > 0:
            a["reload"] -= dt
            if a["reload"] <= 0:
                a["loaded"] = True
        elif it.attack and a["loaded"] and self.ammo > 0 and self.stagger <= 0:
            game.fire_arrow(self, it.aim, 1.0, kind="bolt")
            self.ammo -= 1
            a["loaded"] = False
            a["reload"] = 2.2

    def _update_mounted(self, game, dt):
        m = self.mount
        it = self.intent
        m.ride_control(game, self, it, dt)
        self.x = m.cx - self.w / 2
        self.y = m.y - self.h + 14
        self.vx, self.vy = m.vx, m.vy
        self.facing = m.facing
        self.walk_phase = m.walk_phase
        self.stamina = min(self.max_stamina, self.stamina + 15 * dt)
        if it.attack and self.weapon_def.kind not in ("bow", "crossbow"):
            self.start_attack(game)
        if self.action is not None and self.action["kind"] == "attack":
            self._advance_attack(game, dt)
        elif self.weapon_def.kind == "bow":
            self._update_bow(game, dt)
        self.blocking = it.block and self.weapon_def.kind == "melee"
        self.state = "ride"
        self.pose = compute_pose(self)

    def _environment(self, game, dt):
        # landing damage
        if self.on_ground and self.landed_speed > 0:
            fall = (self.y - self.fall_peak) / TILE
            if fall > 9 and self.in_water < 0.2 and not getattr(self, "skyfall", False):
                dmg = (fall - 9) * 7
                self.hp -= dmg
                self.hurt_flash = 0.2
                game.fx.number(self.cx, self.y - 4, int(dmg))
                if self.hp <= 0:
                    self.die(game, None)
            self.landed_speed = 0
            self.fall_peak = self.y
        # drowning
        if self.head_under:
            self.breath -= dt
            if self.breath <= 0:
                self.drowning_tick -= dt
                if self.drowning_tick <= 0:
                    self.drowning_tick = 1.0
                    self.hp -= 10
                    self.hurt_flash = 0.2
                    if self.hp <= 0:
                        self.die(game, None)
        else:
            self.breath = min(12.0, self.breath + dt * 4)
        if self.in_lava:
            self.hp -= 60 * dt
            self.vy = min(self.vy, -100)
            game.fx.fire(self.cx, self.feet - 6, 2)
            if self.hp <= 0:
                self.die(game, None)
        tx, ty = int(self.cx // TILE), int(self.cy // TILE)
        if (tx, ty) in game.world.fires or (tx, ty + 1) in game.world.fires:
            self.hp -= 12 * dt
            if self.hp <= 0:
                self.die(game, None)

    def _classify(self, dt):
        sp = abs(self.vx)
        if self.stagger > 0.3:
            self.state = "stagger"
        elif self.slide_t > 0:
            self.state = "slide"
        elif self.climbing:
            self.state = "climb"
        elif self.in_water > 0.5 and not self.on_ground:
            self.state = "swim"
        elif not self.on_ground and self.in_water < 0.3:
            self.state = "jump" if self.vy < 0 else "fall"
        elif self.h == CROUCH_H:
            self.state = "crouch"
        elif sp > WALK_SPEED * 1.15:
            self.state = "run"
        elif sp > 8:
            self.state = "walk"
        elif self.action and self.action["kind"] == "work":
            self.state = "work"
        else:
            self.state = getattr(self, "rest_state", None) or "idle"
        if self.state in ("walk", "run", "crouch"):
            self.walk_phase += sp * dt * (0.14 if self.state != "run" else 0.085)

    # ---------------------------------------------------------------- misc
    def say(self, text, gloss=None, t=4.0):
        self.bubble = [text, t, gloss]

    def light_strength(self):
        if self.weapon_key == "fackel" and not self.dead:
            return 0.95
        return self.carry_light
