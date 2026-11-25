"""Weapon, shield and armour definitions. Each weapon class has its own mechanics.

Moves are chosen from the fighter's *state* (no complicated key combos):
    standing  -> 3-hit combo (swing, backswing, overhead)
    running   -> lunge / thrust (charge)
    crouching -> low sweep, or a riposte (Konter) right after a successful block
    airborne  -> plunging strike
    mounted   -> couched lance / riding slash
"""
from dataclasses import dataclass, field


@dataclass
class Move:
    key: str
    windup: float
    active: float
    recover: float
    reach: float
    dmg: float = 1.0           # multiplier of weapon damage
    arc: str = "swing"         # swing / backswing / overhead / thrust / low / plunge / stab
    lunge: float = 0.0         # forward impulse px/s
    posture: float = 1.0
    stamina: float = 1.0


@dataclass
class WeaponDef:
    key: str
    de: str
    en: str
    kind: str = "melee"        # melee / bow / crossbow / tool / torch
    dmg: float = 10
    dtype: str = "cut"         # cut / pierce / blunt
    reach: float = 36
    speed: float = 1.0         # >1 faster
    block: float = 0.55        # fraction of damage stopped when blocking with the weapon itself
    stamina: float = 12
    posture: float = 14
    two_handed: bool = False
    length: float = 30         # drawing length in px
    flags: tuple = ()
    tool_power: dict = field(default_factory=dict)  # {"pick": 2.0, "axe": 3.0}
    style: str = "sword"       # renderer
    note: str = ""


def moves_for(w: WeaponDef):
    s = 1.0 / w.speed
    r = w.reach
    if w.kind in ("bow", "crossbow"):
        return {}
    if "polearm" in w.flags:
        return {
            "combo": [Move("stoss", 0.24 * s, 0.12, 0.30 * s, r, 1.0, "thrust", 90, 0.9),
                      Move("stoss2", 0.20 * s, 0.12, 0.30 * s, r, 1.0, "thrust", 60, 0.9),
                      Move("hieb", 0.40 * s, 0.14, 0.42 * s, r * 0.9, 1.35, "overhead", 40, 1.5, 1.4)],
            "run": Move("anlauf", 0.14 * s, 0.22, 0.45 * s, r * 1.05, 1.6, "thrust", 260, 1.4, 1.3),
            "crouch": Move("tief", 0.18 * s, 0.12, 0.30 * s, r * 0.95, 0.9, "low", 30, 1.2),
            "air": Move("sturz", 0.10, 0.20, 0.35, r * 0.7, 1.4, "plunge", 0, 1.6),
            "riposte": Move("konter", 0.08, 0.14, 0.26, r, 1.9, "thrust", 120, 2.0, 0.6),
        }
    if "dagger" in w.flags:
        return {
            "combo": [Move("stich", 0.10 * s, 0.08, 0.16 * s, r, 1.0, "stab", 70),
                      Move("stich2", 0.08 * s, 0.08, 0.16 * s, r, 1.0, "stab", 70),
                      Move("schnitt", 0.14 * s, 0.10, 0.24 * s, r, 1.4, "swing", 60, 1.0)],
            "run": Move("sprung", 0.10, 0.16, 0.30, r * 1.2, 1.5, "stab", 300, 1.0),
            "crouch": Move("tief", 0.10, 0.08, 0.18, r, 1.0, "low", 40),
            "air": Move("sturz", 0.06, 0.18, 0.26, r, 1.6, "plunge", 0),
            "riposte": Move("konter", 0.05, 0.10, 0.20, r, 2.2, "stab", 120, 1.5, 0.5),
        }
    return {
        "combo": [Move("hieb", 0.20 * s, 0.12, 0.26 * s, r, 1.0, "swing", 70),
                  Move("rueckhieb", 0.16 * s, 0.12, 0.26 * s, r, 1.0, "backswing", 60),
                  Move("oberhau", 0.34 * s, 0.14, 0.40 * s, r * 1.05, 1.5, "overhead", 90, 1.6, 1.4)],
        "run": Move("ansturm", 0.12 * s, 0.20, 0.40 * s, r * 1.15, 1.45, "thrust", 300, 1.3, 1.3),
        "crouch": Move("unterhau", 0.14 * s, 0.12, 0.28 * s, r * 0.95, 0.85, "low", 40, 1.3),
        "air": Move("sturzhieb", 0.10, 0.22, 0.32, r, 1.5, "plunge", 0, 1.8),
        "riposte": Move("konter", 0.06, 0.12, 0.24, r, 1.9, "swing", 140, 2.0, 0.6),
    }


WEAPONS = {}


def _w(**kw):
    wd = WeaponDef(**kw)
    WEAPONS[wd.key] = wd
    return wd


_w(key="fists", de="Fäuste", en="fists", dmg=5, dtype="blunt", reach=22, speed=1.4, block=0.25, stamina=8,
   posture=8, length=0, style="none")
_w(key="knueppel", de="Knüppel", en="cudgel", dmg=10, dtype="blunt", reach=32, speed=1.1, block=0.4, length=26,
   style="club")
_w(key="schwert", de="Schwert", en="arming sword", dmg=17, dtype="cut", reach=42, speed=1.0, block=0.62,
   length=34, style="sword", note="Balanced. Parries well.")
_w(key="langschwert", de="Langschwert", en="longsword", dmg=24, dtype="cut", reach=54, speed=0.82, block=0.7,
   two_handed=True, stamina=16, posture=20, length=46, style="longsword", note="Two hands, long reach.")
_w(key="dolch", de="Dolch", en="dagger", dmg=10, dtype="pierce", reach=24, speed=1.6, block=0.3, stamina=7,
   length=14, flags=("dagger", "backstab"), style="dagger", note="x3 from behind on an unaware target.")
_w(key="axt", de="Axt", en="axe", dmg=21, dtype="cut", reach=38, speed=0.85, block=0.4, stamina=15, posture=22,
   length=30, flags=("shieldbreak",), tool_power={"axe": 3.0}, style="axe",
   note="Smashes shields and guards. Fells trees.")
_w(key="streitkolben", de="Streitkolben", en="mace", dmg=17, dtype="blunt", reach=36, speed=0.95, block=0.45,
   stamina=14, posture=26, length=28, flags=("armorbreak",), style="mace", note="Ignores much of any armour.")
_w(key="flegel", de="Dreschflegel", en="threshing flail", dmg=13, dtype="blunt", reach=44, speed=0.9, block=0.2,
   stamina=13, posture=18, length=36, flags=("wrap",), style="flail",
   note="A farm tool. Wraps around shields.")
_w(key="mistgabel", de="Mistgabel", en="pitchfork", dmg=10, dtype="pierce", reach=58, speed=1.0, block=0.35,
   length=50, flags=("polearm",), style="fork", note="A peasant's spear.")
_w(key="speer", de="Speer", en="spear", dmg=15, dtype="pierce", reach=66, speed=1.0, block=0.45, length=58,
   flags=("polearm", "brace"), style="spear", note="Crouch + block to brace against a charge.")
_w(key="spiess", de="Langspieß", en="pike", dmg=16, dtype="pierce", reach=98, speed=0.75, block=0.35,
   two_handed=True, length=90, stamina=15, flags=("polearm", "brace", "pike"), style="pike",
   note="Huge reach; deadly in formation, clumsy alone.")
_w(key="hellebarde", de="Hellebarde", en="halberd", dmg=23, dtype="cut", reach=76, speed=0.78, block=0.5,
   two_handed=True, length=70, stamina=17, posture=24, flags=("polearm", "hook", "brace"), style="halberd",
   note="Hooks riders off their horses.")
_w(key="lanze", de="Lanze", en="lance", dmg=20, dtype="pierce", reach=84, speed=0.7, block=0.2, length=86,
   flags=("polearm", "lance"), style="lance", note="Damage grows with your horse's speed.")
_w(key="bogen", de="Bogen", en="bow", kind="bow", dmg=16, dtype="pierce", reach=0, length=34, style="bow",
   note="Hold to draw. Wind carries arrows; rain wets the string.")
_w(key="armbrust", de="Armbrust", en="crossbow", kind="crossbow", dmg=28, dtype="pierce", reach=0, length=30,
   flags=("armorpierce",), style="crossbow", note="Slow to span, punches through mail.")
_w(key="spitzhacke", de="Spitzhacke", en="pickaxe", kind="tool", dmg=8, dtype="pierce", reach=34, speed=1.0,
   length=26, tool_power={"pick": 3.0, "axe": 0.8}, style="pick")
_w(key="hammer", de="Hammer", en="hammer", kind="tool", dmg=9, dtype="blunt", reach=30, speed=1.1, length=22,
   tool_power={"pick": 1.2, "axe": 1.2}, style="hammer")
_w(key="sichel", de="Sichel", en="sickle", kind="tool", dmg=7, dtype="cut", reach=28, speed=1.3, length=18,
   tool_power={"axe": 1.0}, style="sickle")
_w(key="hacke", de="Hacke", en="hoe", kind="tool", dmg=6, dtype="cut", reach=30, speed=1.1, length=24,
   tool_power={"pick": 0.8}, style="hoe", note="Turns grass into a field (Acker).")
_w(key="schaufel", de="Schaufel", en="shovel", kind="tool", dmg=7, dtype="blunt", reach=30, speed=1.2, length=26,
   tool_power={"pick": 1.0}, style="shovel", note="Digs earth fast, rock slowly. Throw the earth back to fill a hole.")
_w(key="fackel", de="Fackel", en="torch", kind="torch", dmg=6, dtype="blunt", reach=30, speed=1.1, length=20,
   flags=("fire",), style="torch", note="Lights the dark — and sets thatch ablaze.")

for _wd in WEAPONS.values():
    _wd.moves = moves_for(_wd)


@dataclass
class ShieldDef:
    key: str
    de: str
    en: str
    block: float           # damage fraction stopped
    arrow_block: float     # chance to stop arrows from the front
    weight: float
    size: float
    style: str = "round"


SHIELDS = {
    "holzschild": ShieldDef("holzschild", "Holzschild", "round shield", 0.85, 0.75, 0.1, 13, "round"),
    "dreieckschild": ShieldDef("dreieckschild", "Dreieckschild", "heater shield", 0.9, 0.85, 0.12, 15, "heater"),
    "pavese": ShieldDef("pavese", "Pavese", "pavise", 0.95, 0.97, 0.25, 22, "pavise"),
}


@dataclass
class ArmorDef:
    key: str
    de: str
    en: str
    cut: float
    pierce: float
    blunt: float
    weight: float
    color: tuple
    style: str = "cloth"


ARMORS = {
    "kleidung": ArmorDef("kleidung", "Kleidung", "clothes", 0.0, 0.0, 0.0, 0.0, (0, 0, 0), "cloth"),
    "gambeson": ArmorDef("gambeson", "Gambeson", "padded jacket", 0.3, 0.2, 0.25, 0.05, (200, 186, 150), "gambeson"),
    "kettenhemd": ArmorDef("kettenhemd", "Kettenhemd", "mail shirt", 0.6, 0.35, 0.15, 0.18, (150, 154, 160), "mail"),
    "plattenrock": ArmorDef("plattenrock", "Plattenrock", "coat of plates", 0.78, 0.55, 0.3, 0.3, (170, 176, 186),
                            "plate"),
}

HELMETS = {
    None: (0.0, None),
    "kettenhaube": (0.08, "coif"),
    "eisenhut": (0.12, "kettle"),
    "beckenhaube": (0.14, "bascinet"),
    "topfhelm": (0.2, "greathelm"),
}
HELMET_NAMES = {"kettenhaube": ("Kettenhaube", "mail coif"), "eisenhut": ("Eisenhut", "kettle hat"),
                "beckenhaube": ("Beckenhaube", "bascinet"), "topfhelm": ("Topfhelm", "great helm")}
