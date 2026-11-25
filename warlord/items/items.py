"""Item registry. German name first — the inventory is a vocabulary lesson."""
from dataclasses import dataclass

from ..combat.weapons import WEAPONS, SHIELDS, ARMORS, HELMET_NAMES


@dataclass
class ItemDef:
    key: str
    de: str
    en: str
    cat: str            # material food weapon tool shield armor helmet place ammo money mount misc
    value: int = 1      # base price in Pfennig
    stack: int = 99
    place: str = None   # what it becomes in the world: 'object' (a physics piece), 'seed', 'plant', 'station'
    food: float = 0.0
    weapon: str = None
    color: tuple = (180, 160, 120)
    icon: str = "lump"


ITEMS = {}


def _i(key, de, en, cat, value=1, **kw):
    ITEMS[key] = ItemDef(key, de, en, cat, value, **kw)


# materials
_i("wood", "Holz", "wood", "material", 1, color=(140, 98, 58), icon="log")
_i("planks", "Bretter", "planks", "place", 2, place="object", color=(170, 124, 72), icon="block")
_i("stone", "Stein", "stone", "place", 1, place="object", color=(130, 128, 124), icon="block")
_i("dirt", "Erde", "earth", "place", 0, place="object", color=(112, 78, 52), icon="block")
_i("sand", "Sand", "sand", "place", 0, place="object", color=(214, 192, 132), icon="block")
_i("clay", "Lehm", "clay", "material", 1, color=(160, 104, 80), icon="lump")
_i("brick", "Mauerstein", "stone brick", "place", 4, place="object", color=(150, 146, 136), icon="block")
_i("straw", "Stroh", "straw", "place", 1, place="object", color=(196, 164, 84), icon="block")
_i("rooftile", "Ziegel", "roof tile", "place", 3, place="object", color=(164, 66, 48), icon="block")
_i("slate", "Schiefer", "slate", "place", 3, place="object", color=(70, 78, 92), icon="block")
_i("fachwerk", "Fachwerk", "timber frame", "place", 4, place="object", color=(232, 222, 196), icon="block")
_i("palisade", "Palisade", "palisade stake", "place", 3, place="object", color=(110, 80, 50), icon="block")
_i("door", "Tür", "door", "place", 8, place="object", color=(120, 80, 46), icon="block")
_i("ladder", "Leiter", "ladder", "place", 3, place="object", color=(140, 100, 60), icon="ladder")
_i("platform", "Steg", "plank walk", "place", 1, place="object", color=(150, 108, 64), icon="block")
_i("torch", "Fackel", "torch", "weapon", 2, place="object", weapon="fackel", color=(255, 180, 60), icon="torch")
_i("coal", "Kohle", "coal", "material", 2, color=(40, 40, 44), icon="lump")
_i("iron_ore", "Eisenerz", "iron ore", "material", 4, color=(176, 120, 92), icon="lump")
_i("silver_ore", "Silbererz", "silver ore", "material", 12, color=(214, 220, 228), icon="lump")
_i("gold_ore", "Golderz", "gold ore", "material", 30, color=(240, 200, 70), icon="lump")
_i("iron_ingot", "Eisenbarren", "iron bar", "material", 12, color=(160, 164, 172), icon="ingot")
_i("silver_coin", "Silbermünze", "silver coin", "money", 1, stack=9999, color=(220, 220, 230), icon="coin")
_i("salt", "Salz", "salt", "material", 6, color=(236, 232, 226), icon="lump")
_i("glutstein", "Glutstein", "ember stone", "material", 25, color=(255, 120, 40), icon="lump")
_i("obsidian", "Obsidian", "obsidian", "place", 8, place="object", color=(54, 34, 70), icon="block")
_i("floatstone", "Schwebestein", "float stone", "material", 40, color=(170, 160, 200), icon="lump")
_i("ash", "Asche", "ash", "material", 0, color=(90, 86, 84), icon="lump")
_i("snowball", "Schneeball", "snowball", "material", 0, color=(240, 240, 250), icon="lump")
_i("rope", "Seil", "rope", "material", 3, color=(190, 160, 110), icon="lump")
_i("cloth", "Tuch", "cloth", "material", 5, color=(200, 190, 170), icon="lump")
_i("wool", "Wolle", "wool", "material", 2, color=(236, 230, 220), icon="lump")
_i("leather", "Leder", "leather", "material", 4, color=(130, 86, 50), icon="lump")
_i("hay", "Heu", "hay", "place", 1, place="object", color=(210, 184, 96), icon="block")
_i("seeds", "Saatgut", "seeds", "place", 1, place="seed", color=(170, 150, 80), icon="seeds")
_i("sapling", "Setzling", "sapling", "place", 2, place="plant", color=(90, 140, 60), icon="seeds")
_i("seaweed", "Seegras", "seaweed", "material", 1, color=(50, 110, 70), icon="lump")
_i("shell", "Muschel", "shell", "material", 2, color=(230, 200, 190), icon="lump")
_i("herb", "Kräuter", "herbs", "material", 3, color=(120, 180, 90), icon="lump")
# food
_i("wheat", "Weizen", "wheat", "material", 2, color=(222, 190, 84), icon="sheaf")
_i("rye", "Roggen", "rye", "material", 2, color=(196, 170, 110), icon="sheaf")
_i("oats", "Hafer", "oats", "material", 2, color=(220, 210, 150), icon="sheaf")
_i("flax", "Flachs", "flax", "material", 3, color=(190, 170, 110), icon="sheaf")
_i("turnip", "Rübe", "turnip", "food", 2, food=10, color=(226, 214, 190), icon="berry")
_i("seeds_rye", "Roggensaat", "rye seed", "place", 1, place="seed", color=(170, 150, 100), icon="seeds")
_i("seeds_oat", "Hafersaat", "oat seed", "place", 1, place="seed", color=(200, 190, 140), icon="seeds")
_i("seeds_flax", "Leinsamen", "flax seed", "place", 1, place="seed", color=(150, 120, 80), icon="seeds")
_i("seeds_turnip", "Rübensamen", "turnip seed", "place", 1, place="seed", color=(160, 120, 90),
   icon="seeds")
_i("mist", "Mist", "manure", "misc", 1, color=(90, 70, 40), icon="lump")
_i("pflug", "Pflug", "plough", "misc", 40, stack=1, color=(120, 90, 60), icon="hammer")
_i("flour", "Mehl", "flour", "material", 3, color=(240, 236, 226), icon="sack")
_i("bread", "Brot", "bread", "food", 4, food=30, color=(200, 150, 80), icon="bread")
_i("berries", "Beeren", "berries", "food", 1, food=8, color=(170, 30, 60), icon="berry")
_i("mushroom", "Pilz", "mushroom", "food", 1, food=6, color=(190, 80, 60), icon="berry")
_i("grapes", "Trauben", "grapes", "food", 2, food=10, color=(110, 40, 110), icon="berry")
_i("fish", "Fisch", "fish", "food", 3, food=18, color=(150, 170, 190), icon="fish")
_i("meat", "Fleisch", "meat", "food", 4, food=22, color=(180, 70, 60), icon="meat")
_i("cheese", "Käse", "cheese", "food", 5, food=20, color=(236, 200, 90), icon="bread")
_i("beer", "Bier", "beer", "food", 3, food=6, color=(200, 150, 50), icon="mug")
_i("wine", "Wein", "wine", "food", 8, food=8, color=(120, 20, 40), icon="mug")
# stations / furniture
for key, de, en, val, col in (("workbench", "Werkbank", "workbench", 8, (150, 110, 70)),
                              ("anvil", "Amboss", "anvil", 40, (70, 72, 80)), ("forge", "Esse", "forge", 30,
                                                                              (130, 80, 60)),
                              ("bed", "Bett", "bed", 15, (160, 60, 50)), ("chest", "Truhe", "chest", 10, (120, 80, 46)),
                              ("table", "Tisch", "table", 6, (130, 90, 56)), ("barrel", "Fass", "barrel", 5,
                                                                            (120, 80, 48)),
                              ("oven", "Ofen", "oven", 25, (150, 90, 70)), ("loom", "Webstuhl", "loom", 20,
                                                                         (150, 120, 80)),
                              ("campfire", "Feuerstelle", "campfire", 3, (200, 100, 40))):
    _i(key, de, en, "place", val, place="station", color=col, icon="block")
# arrows
_i("arrow", "Pfeil", "arrow", "ammo", 1, color=(200, 190, 170), icon="arrow")
_i("bolt", "Bolzen", "crossbow bolt", "ammo", 2, color=(170, 170, 176), icon="arrow")
_i("fire_arrow", "Brandpfeil", "fire arrow", "ammo", 3, color=(255, 140, 40), icon="arrow")
_i("pech", "Pech", "pitch", "material", 4, color=(30, 26, 24), icon="lump")
_i("schwefel", "Schwefel", "sulphur", "material", 8, color=(230, 214, 60), icon="lump")
_i("salpeter", "Salpeter", "saltpetre", "material", 8, color=(236, 232, 220), icon="lump")
_i("pulver", "Schwarzpulver", "black powder", "material", 30, color=(40, 40, 40), icon="sack")
_i("kugel", "Steinkugel", "stone ball", "ammo", 4, color=(150, 146, 136), icon="lump")
_i("stuetze", "Stütze", "mine prop", "place", 2, place="object", color=(124, 86, 48), icon="block")
_i("verband", "Verband", "bandage", "heal", 3, color=(236, 230, 214), icon="lump")
_i("chronik", "Chronik", "the Frostholm chronicle", "misc", 0, stack=1, color=(120, 40, 40), icon="block")
# boats and mounts (deeds)
_i("boat", "Boot", "boat", "mount", 120, stack=1, color=(140, 100, 60), icon="boat")
_i("horse", "Pferd", "horse", "mount", 90, stack=1, color=(120, 80, 50), icon="horse")

# weapons / tools
VALUES = {"hacke": 6, "fists": 0, "knueppel": 4, "schwert": 60, "langschwert": 110, "dolch": 20, "axt": 30, "streitkolben": 55,
          "flegel": 10, "mistgabel": 8, "speer": 22, "spiess": 35, "hellebarde": 70, "lanze": 50, "bogen": 30,
          "armbrust": 80, "spitzhacke": 18, "hammer": 10, "sichel": 8, "fackel": 2}
for wk, wd in WEAPONS.items():
    if wk in ("fists", "fackel"):
        continue
    cat = "tool" if wd.kind == "tool" else "weapon"
    _i(wk, wd.de, wd.en, cat, VALUES.get(wk, 10), stack=1, weapon=wk, color=(190, 190, 200), icon=wd.style)
for sk, sd in SHIELDS.items():
    _i(sk, sd.de, sd.en, "shield", 20 if sk == "holzschild" else 45, stack=1, color=(150, 110, 70), icon="shield")
for ak, ad in ARMORS.items():
    if ak == "kleidung":
        continue
    _i(ak, ad.de, ad.en, "armor", {"gambeson": 25, "kettenhemd": 120, "plattenrock": 260}[ak], stack=1,
       color=ad.color, icon="armor")
for hk, (de, en) in HELMET_NAMES.items():
    _i(hk, de, en, "helmet", {"kettenhaube": 30, "eisenhut": 40, "beckenhaube": 70, "topfhelm": 110}[hk], stack=1,
       color=(160, 164, 170), icon="helmet")


# shaped wood: what you carve from a log in the field or at the workbench (quality travels with them)
_i("log", "Stamm", "log", "material", 3, color=(124, 88, 54), icon="log")
_i("beam", "Balken", "beam", "material", 4, color=(110, 76, 48), icon="log")
_i("stake", "Pfahl", "stake", "place", 2, place="object", color=(130, 94, 58), icon="log")
_i("spike", "Spitzpfahl", "sharpened stake", "place", 3, place="object", color=(140, 100, 60), icon="log")
_i("wedge", "Keil", "wedge", "material", 1, color=(150, 110, 70), icon="lump")
_i("wheel", "Rad", "wheel", "material", 12, color=(130, 92, 56), icon="lump")
_i("handle", "Stiel", "tool handle", "material", 2, color=(150, 112, 70), icon="log")
_i("shaft", "Schaft", "spear shaft", "material", 3, color=(150, 112, 70), icon="log")
_i("bowl", "Schale", "wooden bowl", "material", 2, color=(150, 110, 70), icon="lump")
_i("stool", "Schemel", "stool", "place", 4, place="object", color=(140, 100, 62), icon="block")
_i("trough", "Trog", "trough", "place", 5, place="object", color=(130, 92, 58), icon="block")
_i("sign_board", "Schild", "sign board", "place", 2, place="object", color=(150, 112, 70), icon="block")
_i("iron_bar", "Eisenstange", "iron bar", "material", 12, color=(150, 154, 160), icon="ingot")
_i("chip", "Späne", "wood chips", "material", 0, color=(196, 160, 108), icon="lump")

# how heavy things are in the bag (kg); big things cannot go in the bag at all, you carry them in your arms
WEIGHT = {"wood": 2.0, "log": 12.0, "beam": 6.0, "planks": 1.0, "stone": 2.5, "brick": 2.5, "clay": 1.5,
          "straw": 0.3, "rooftile": 0.8, "slate": 0.8, "fachwerk": 3.0, "palisade": 4.0, "door": 9.0,
          "ladder": 6.0, "platform": 1.0, "iron_ore": 2.0, "silver_ore": 2.0, "gold_ore": 2.0, "coal": 0.6,
          "iron_ingot": 1.5, "iron_bar": 1.5, "silver_coin": 0.0, "stake": 3.0, "spike": 3.0, "wheel": 5.0,
          "stool": 3.0, "trough": 6.0, "pflug": 15.0, "boat": 0.0, "horse": 0.0, "chest": 8.0, "anvil": 30.0,
          "forge": 25.0, "bed": 12.0, "table": 8.0, "barrel": 7.0, "oven": 25.0, "loom": 15.0, "workbench": 15.0,
          "campfire": 3.0, "kugel": 6.0, "chronik": 1.0, "chip": 0.05, "arrow": 0.05, "bolt": 0.08,
          "fire_arrow": 0.06, "seeds": 0.05, "seeds_rye": 0.05, "seeds_oat": 0.05, "seeds_flax": 0.05,
          "seeds_turnip": 0.05, "sapling": 0.4, "torch": 0.6, "verband": 0.1, "mist": 1.0, "rope": 0.5, "cloth": 0.4,
          "wool": 0.3, "leather": 0.6, "straw": 0.3, "hay": 0.5, "salt": 0.5, "pech": 1.0, "pulver": 1.0,
          "handle": 0.6, "shaft": 1.2, "wedge": 0.3, "bowl": 0.4, "sign_board": 1.0, "herb": 0.05,
          "berries": 0.1, "mushroom": 0.1, "shell": 0.05}
CAT_WEIGHT = {"food": 0.4, "material": 0.8, "weapon": 2.5, "tool": 2.0, "shield": 4.0, "armor": 8.0, "helmet": 2.0,
              "ammo": 0.06, "heal": 0.1, "place": 2.0, "misc": 0.5, "money": 0.0, "mount": 0.0}
# too bulky for any bag: carried in both arms
BULKY = {"log", "beam", "door", "ladder", "wheel", "trough", "anvil", "forge", "bed", "table", "oven", "loom",
         "workbench", "palisade", "stake", "spike", "pflug", "chest", "barrel"}


def weight(key):
    if key in WEIGHT:
        return WEIGHT[key]
    d = ITEMS.get(key)
    return CAT_WEIGHT.get(d.cat, 1.0) if d else 1.0


def name(key):
    d = ITEMS.get(key)
    return f"{d.de} ({d.en})" if d else key
