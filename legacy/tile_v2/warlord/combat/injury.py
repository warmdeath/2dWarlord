"""Wunden — injuries, hit locations and armour hardness.

Every blow lands on a body part: head, torso, weapon arm, shield arm or legs. Armour covers some
parts with a *hardness*; every weapon has a *penetration*. A cut that can't beat the hardness
glances off ("Abgeprallt!"), a bodkin or a crossbow bolt punches through mail, a mace ignores
hardness but its blunt trauma is softened by padding. Damage that gets through wounds the part:

    level 1  Wunde          bleeding; arm: weaker blows; legs: no running
    level 2  schwere Wunde  arm: drops weapon/shield; legs: no jumping, limping; head: dazed
    level 3  verkrüppelt    legs: crawling; head: knocked senseless (out of the fight)

Wounds bleed until bandaged (Verband) and heal slowly with rest.
"""
import random

PARTS = ("head", "torso", "arm_w", "arm_s", "legs")
PART_DE = {"head": ("Kopf", "head"), "torso": ("Rumpf", "torso"), "arm_w": ("Schwertarm", "sword arm"),
           "arm_s": ("Schildarm", "shield arm"), "legs": ("Beine", "legs")}
LEVEL_DE = {1: ("Wunde", "wound"), 2: ("schwere Wunde", "severe wound"), 3: ("verkrüppelt", "crippled")}
THRESH = (6.0, 18.0, 34.0)

# armour: part -> hardness (mail and plates are worn over padding)
ARMOR_COVER = {
    "kleidung": {},
    "gambeson": {"torso": 2, "arm_w": 2, "arm_s": 2},
    "kettenhemd": {"torso": 5, "arm_w": 5, "arm_s": 5, "legs": 4},
    "plattenrock": {"torso": 8, "arm_w": 5, "arm_s": 5, "legs": 5},
}
HELMET_HARD = {"kettenhaube": 5, "eisenhut": 7, "beckenhaube": 8, "topfhelm": 9}

# penetration by weapon / missile
PEN = {"fists": 0, "knueppel": 1, "schwert": 4, "langschwert": 5, "dolch": 6, "axt": 5, "streitkolben": 2,
       "flegel": 2, "mistgabel": 3, "speer": 5, "spiess": 5, "hellebarde": 6, "lanze": 7, "bogen": 5,
       "armbrust": 8, "spitzhacke": 4, "hammer": 2, "sichel": 2, "fackel": 0, "sense": 3, "hacke": 2,
       "arrow": 5, "fire_arrow": 4, "bolt": 8, "ball": 11, "stone": 3, "animal": 3}


def level(w):
    return 3 if w >= THRESH[2] else 2 if w >= THRESH[1] else 1 if w >= THRESH[0] else 0


def hit_part(t, hit_y, high=True):
    """Which part a blow at height hit_y lands on."""
    if hit_y is None:
        hit_y = t.y + (t.h * 0.3 if high else t.h * 0.8)
    rel = (hit_y - t.y) / max(1.0, t.h)
    if rel < 0.22:
        return "head"
    if rel < 0.6:
        r = random.random()
        if r < 0.18:
            return "arm_w"
        if r < 0.30:
            return "arm_s"
        return "torso"
    return "legs"


def hardness(t, part):
    if part == "head":
        return HELMET_HARD.get(t.helmet, 0) if t.helmet else 0
    return ARMOR_COVER.get(t.armor.key if t.armor else "kleidung", {}).get(part, 0)


def armour(t, part, dtype, pen, flags=()):
    """-> fraction of damage that gets through, hardness."""
    H = hardness(t, part)
    if "armorpierce" in flags:
        pen += 2
    if H <= 0:
        return 1.0, 0
    if dtype == "blunt":
        f = max(0.35, 1.0 - H * 0.07)
        if "armorbreak" in flags:
            f = max(f, 0.75)
        return f, H
    if pen >= H:
        return 0.72 + 0.28 * min(1.0, (pen - H) / 3.0), H
    return max(0.04, 0.38 * (pen / H) ** 2), H


def wound(t, part, dmg, game):
    """Apply damage that got through to a part; returns the new level."""
    w = t.wounds.get(part, 0.0) + dmg * (1.3 if part == "head" else 1.0)
    t.wounds[part] = w
    old = t.injury.get(part, 0)
    lv = level(w)
    if lv > old:
        t.injury[part] = lv
        t.bandaged = False
        de, en = PART_DE[part]
        lde, len_ = LEVEL_DE[lv]
        if game is not None and (t is game.player or lv >= 2):
            game.fx.text(t.cx, t.y - 30, f"{de}: {lde}", (255, 140, 120), gloss=f"{en}: {len_}", life=1.8)
        if part == "arm_w" and lv >= 2 and t.weapon_key not in ("fists",):
            if game is not None:
                game.drop_item(t.weapon_key, 1, t.cx, t.y + 10) if t is not game.player else None
                if t is game.player:
                    game.ui.toast("Your sword arm is badly wounded — you can barely hold a weapon. "
                                  "([Verband|bandage] it!)")
            if t is not getattr(game, "player", None):
                t.equip(weapon="fists")
        if part == "arm_s" and lv >= 2 and t.shield is not None:
            t.equip(shield="")
        if part == "head" and lv >= 2:
            t.stagger = max(t.stagger, 1.2)
        if part == "head" and lv >= 3:
            t.hp = 0
    return t.injury.get(part, 0)


def speed_factor(t):
    lv = t.injury.get("legs", 0) if t.injury else 0
    return (1.0, 0.75, 0.5, 0.3)[lv]


def can_run(t):
    return not t.injury or t.injury.get("legs", 0) < 1


def can_jump(t):
    return not t.injury or t.injury.get("legs", 0) < 2


def damage_factor(t):
    lv = t.injury.get("arm_w", 0) if t.injury else 0
    return (1.0, 0.8, 0.55, 0.4)[lv]


def tick(t, dt, game):
    """Bleeding and slow healing."""
    if not t.injury:
        return
    bleed = 0.0
    for part, lv in t.injury.items():
        if lv >= 1:
            bleed += 0.16 * lv * (1.6 if part == "torso" else 1.0)
    if bleed and not t.bandaged:
        t.hp -= bleed * dt
        if game is not None and random.random() < dt * bleed * 2:
            game.fx.blood(t.cx, t.y + 20, 1, random.choice((-1, 1)))
        if t.hp <= 0:
            t.die(game, getattr(t, "last_attacker", None))
            return
    heal = dt * (0.06 if t.bandaged else 0.015)
    for part in list(t.wounds):
        t.wounds[part] = max(0.0, t.wounds[part] - heal)
        lv = level(t.wounds[part])
        if lv < t.injury.get(part, 0):
            t.injury[part] = lv
        if t.wounds[part] <= 0:
            del t.wounds[part]
            t.injury.pop(part, None)


def bandage(t):
    t.bandaged = True
    for part in list(t.wounds):
        t.wounds[part] *= 0.8
        t.injury[part] = level(t.wounds[part])
        if t.injury[part] == 0:
            t.injury.pop(part)


def rest(t, hours=8):
    for part in list(t.wounds):
        t.wounds[part] = max(0.0, t.wounds[part] - 5 * hours)
        lv = level(t.wounds[part])
        if lv == 0:
            t.wounds.pop(part)
            t.injury.pop(part, None)
        else:
            t.injury[part] = lv
