"""Item registry. German name first — the inventory is a vocabulary lesson."""
from dataclasses import dataclass

from ..world import tiles as T
from ..combat.weapons import WEAPONS, SHIELDS, ARMORS, HELMET_NAMES


@dataclass
class ItemDef:
    key: str
    de: str
    en: str
    cat: str            # material food weapon tool shield armor helmet place ammo money mount misc
    value: int = 1      # base price in Pfennig
    stack: int = 99
    place: int = None   # tile id when placed
    food: float = 0.0
    weapon: str = None
    color: tuple = (180, 160, 120)
    icon: str = "lump"


ITEMS = {}


def _i(key, de, en, cat, value=1, **kw):
    ITEMS[key] = ItemDef(key, de, en, cat, value, **kw)


# materials
_i("wood", "Holz", "wood", "material", 1, color=(140, 98, 58), icon="log")
_i("planks", "Bretter", "planks", "place", 2, place=T.PLANKS.id, color=(170, 124, 72), icon="block")
_i("stone", "Stein", "stone", "place", 1, place=T.STONE.id, color=(130, 128, 124), icon="block")
_i("dirt", "Erde", "earth", "place", 0, place=T.DIRT.id, color=(112, 78, 52), icon="block")
_i("sand", "Sand", "sand", "place", 0, place=T.SAND.id, color=(214, 192, 132), icon="block")
_i("clay", "Lehm", "clay", "material", 1, color=(160, 104, 80), icon="lump")
_i("brick", "Mauerstein", "stone brick", "place", 4, place=T.BRICK.id, color=(150, 146, 136), icon="block")
_i("straw", "Stroh", "straw", "place", 1, place=T.THATCH.id, color=(196, 164, 84), icon="block")
_i("rooftile", "Ziegel", "roof tile", "place", 3, place=T.ROOFTILE.id, color=(164, 66, 48), icon="block")
_i("slate", "Schiefer", "slate", "place", 3, place=T.SLATE.id, color=(70, 78, 92), icon="block")
_i("fachwerk", "Fachwerk", "timber frame", "place", 4, place=T.FACHWERK.id, color=(232, 222, 196), icon="block")
_i("palisade", "Palisade", "palisade stake", "place", 3, place=T.PALISADE.id, color=(110, 80, 50), icon="block")
_i("door", "Tür", "door", "place", 8, place=T.DOOR.id, color=(120, 80, 46), icon="block")
_i("ladder", "Leiter", "ladder", "place", 3, place=T.LADDER.id, color=(140, 100, 60), icon="ladder")
_i("platform", "Steg", "plank walk", "place", 1, place=T.PLATFORM.id, color=(150, 108, 64), icon="block")
_i("torch", "Fackel", "torch", "weapon", 2, place=T.TORCH.id, weapon="fackel", color=(255, 180, 60), icon="torch")
_i("coal", "Kohle", "coal", "material", 2, color=(40, 40, 44), icon="lump")
_i("iron_ore", "Eisenerz", "iron ore", "material", 4, color=(176, 120, 92), icon="lump")
_i("silver_ore", "Silbererz", "silver ore", "material", 12, color=(214, 220, 228), icon="lump")
_i("gold_ore", "Golderz", "gold ore", "material", 30, color=(240, 200, 70), icon="lump")
_i("iron_ingot", "Eisenbarren", "iron bar", "material", 12, color=(160, 164, 172), icon="ingot")
_i("silver_coin", "Silbermünze", "silver coin", "money", 1, stack=9999, color=(220, 220, 230), icon="coin")
_i("salt", "Salz", "salt", "material", 6, color=(236, 232, 226), icon="lump")
_i("glutstein", "Glutstein", "ember stone", "material", 25, color=(255, 120, 40), icon="lump")
_i("obsidian", "Obsidian", "obsidian", "place", 8, place=T.OBSIDIAN.id, color=(54, 34, 70), icon="block")
_i("floatstone", "Schwebestein", "float stone", "material", 40, color=(170, 160, 200), icon="lump")
_i("ash", "Asche", "ash", "material", 0, color=(90, 86, 84), icon="lump")
_i("snowball", "Schneeball", "snowball", "material", 0, color=(240, 240, 250), icon="lump")
_i("rope", "Seil", "rope", "material", 3, color=(190, 160, 110), icon="lump")
_i("cloth", "Tuch", "cloth", "material", 5, color=(200, 190, 170), icon="lump")
_i("wool", "Wolle", "wool", "material", 2, color=(236, 230, 220), icon="lump")
_i("leather", "Leder", "leather", "material", 4, color=(130, 86, 50), icon="lump")
_i("hay", "Heu", "hay", "place", 1, place=T.HAY.id, color=(210, 184, 96), icon="block")
_i("seeds", "Saatgut", "seeds", "place", 1, place=T.WHEAT1.id, color=(170, 150, 80), icon="seeds")
_i("sapling", "Setzling", "sapling", "place", 2, place=T.SAPLING.id, color=(90, 140, 60), icon="seeds")
_i("seaweed", "Seegras", "seaweed", "material", 1, color=(50, 110, 70), icon="lump")
_i("shell", "Muschel", "shell", "material", 2, color=(230, 200, 190), icon="lump")
_i("herb", "Kräuter", "herbs", "material", 3, color=(120, 180, 90), icon="lump")
# food
_i("wheat", "Weizen", "wheat", "material", 2, color=(222, 190, 84), icon="sheaf")
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
for key, tile, val in (("workbench", T.WORKBENCH, 8), ("anvil", T.ANVIL, 40), ("forge", T.FORGE, 30),
                       ("bed", T.BED, 15), ("chest", T.CHEST, 10), ("table", T.TABLE, 6), ("barrel", T.BARREL, 5),
                       ("oven", T.OVEN, 25), ("loom", T.LOOM, 20), ("campfire", T.FIRE_PIT, 3)):
    _i(key, tile.de, tile.en, "place", val, place=tile.id, color=tile.color, icon="block")
# arrows
_i("arrow", "Pfeil", "arrow", "ammo", 1, color=(200, 190, 170), icon="arrow")
_i("bolt", "Bolzen", "crossbow bolt", "ammo", 2, color=(170, 170, 176), icon="arrow")
_i("fire_arrow", "Brandpfeil", "fire arrow", "ammo", 3, color=(255, 140, 40), icon="arrow")
_i("chronik", "Chronik", "the Frostholm chronicle", "misc", 0, stack=1, color=(120, 40, 40), icon="block")
# boats and mounts (deeds)
_i("boat", "Boot", "boat", "mount", 120, stack=1, color=(140, 100, 60), icon="boat")
_i("horse", "Pferd", "horse", "mount", 90, stack=1, color=(120, 80, 50), icon="horse")

# weapons / tools
VALUES = {"fists": 0, "knueppel": 4, "schwert": 60, "langschwert": 110, "dolch": 20, "axt": 30, "streitkolben": 55,
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


def name(key):
    d = ITEMS.get(key)
    return f"{d.de} ({d.en})" if d else key
