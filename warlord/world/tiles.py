"""Tile registry. Each tile is pure data; behaviour tables are baked into numpy lookups."""
from dataclasses import dataclass, field
import numpy as np


@dataclass
class TileDef:
    id: int
    key: str
    de: str                 # German name (shown in UI — you learn it by mining it!)
    en: str
    color: tuple
    solid: bool = True
    natural: bool = False   # natural terrain gets rounded "smooth" corners
    hardness: float = 1.0   # seconds of mining with bare hands (tools divide this)
    drop: str = None        # item key dropped when broken
    flammable: bool = False
    light: float = 0.0      # light emitted 0..1
    platform: bool = False  # one-way platform
    climbable: bool = False
    falls: bool = False     # sand-like gravity
    built: bool = False     # man-made: obeys structural support rules
    style: str = "noise"    # renderer pattern
    tool: str = "pick"      # best tool: pick/axe/hand
    color2: tuple = None
    deco: bool = False      # non-solid decoration rendered as sprite
    extra: dict = field(default_factory=dict)


TILES = {}
BY_KEY = {}


def _t(*args, **kw):
    t = TileDef(*args, **kw)
    TILES[t.id] = t
    BY_KEY[t.key] = t
    return t


AIR = _t(0, "air", "Luft", "air", (0, 0, 0), solid=False, hardness=0)
DIRT = _t(1, "dirt", "Erde", "earth", (112, 78, 52), natural=True, hardness=0.5, drop="dirt", tool="pick")
GRASS = _t(2, "grass", "Gras", "grass", (112, 78, 52), natural=True, hardness=0.5, drop="dirt", style="grass",
           color2=(86, 140, 58))
STONE = _t(3, "stone", "Stein", "stone", (118, 116, 112), natural=True, hardness=1.6, drop="stone")
SAND = _t(4, "sand", "Sand", "sand", (214, 192, 132), natural=True, hardness=0.4, drop="sand", falls=True)
GRAVEL = _t(5, "gravel", "Kies", "gravel", (130, 122, 112), natural=True, hardness=0.6, drop="stone", falls=True,
            style="gravel")
CLAY = _t(6, "clay", "Lehm", "clay", (160, 104, 80), natural=True, hardness=0.6, drop="clay")
SNOW = _t(7, "snow", "Schnee", "snow", (236, 240, 246), natural=True, hardness=0.3, drop="snowball")
ICE = _t(8, "ice", "Eis", "ice", (170, 210, 236), natural=True, hardness=0.8, drop=None, style="ice")
ASH = _t(9, "ash", "Asche", "ash", (88, 82, 80), natural=True, hardness=0.4, drop="ash", style="grass",
         color2=(60, 56, 56))
BASALT = _t(10, "basalt", "Basalt", "basalt", (52, 48, 52), natural=True, hardness=2.2, drop="stone")
MUD = _t(11, "mud", "Schlamm", "mud", (74, 62, 44), natural=True, hardness=0.4, drop="dirt", style="grass",
         color2=(70, 96, 56))
BEDROCK = _t(12, "bedrock", "Grundfels", "bedrock", (36, 32, 36), natural=True, hardness=9999)
COAL = _t(13, "coal_ore", "Kohle", "coal", (118, 116, 112), natural=True, hardness=1.8, drop="coal", style="ore",
          color2=(30, 30, 32))
IRON = _t(14, "iron_ore", "Eisenerz", "iron ore", (118, 116, 112), natural=True, hardness=2.2, drop="iron_ore",
          style="ore", color2=(176, 120, 92))
SILVER = _t(15, "silver_ore", "Silbererz", "silver ore", (118, 116, 112), natural=True, hardness=2.6,
            drop="silver_ore", style="ore", color2=(214, 220, 228))
GOLD_ORE = _t(16, "gold_ore", "Golderz", "gold ore", (118, 116, 112), natural=True, hardness=3.0, drop="gold_ore",
              style="ore", color2=(240, 200, 70))
SALT = _t(17, "salt", "Salz", "salt", (226, 220, 214), natural=True, hardness=1.0, drop="salt", style="crystal")
GLUTSTEIN = _t(18, "glutstein", "Glutstein", "ember stone", (70, 40, 36), natural=True, hardness=3.5,
               drop="glutstein", style="ore", color2=(255, 120, 40), light=0.45)
LOG = _t(19, "log", "Stamm", "tree trunk", (96, 66, 42), solid=False, hardness=1.2, drop="wood", flammable=True,
         style="bark", tool="axe")
LEAVES = _t(20, "leaves", "Laub", "leaves", (60, 112, 52), solid=False, hardness=0.1, drop=None, flammable=True,
            style="leaves", tool="axe")
PINE = _t(21, "pine", "Nadeln", "pine needles", (40, 84, 62), solid=False, hardness=0.1, drop=None,
          flammable=True, style="leaves", tool="axe")
PLANKS = _t(22, "planks", "Bretter", "planks", (156, 112, 66), hardness=0.8, drop="planks", flammable=True,
            built=True, style="planks", tool="axe")
BRICK = _t(23, "brick", "Mauerstein", "stone brick", (150, 146, 136), hardness=3.0, drop="brick", built=True,
           style="brick")
FACHWERK = _t(24, "fachwerk", "Fachwerk", "timber frame", (232, 222, 196), hardness=1.0, drop="planks",
              flammable=True, built=True, style="fachwerk", tool="axe", color2=(78, 52, 34))
THATCH = _t(25, "thatch", "Stroh", "straw", (196, 164, 84), hardness=0.4, drop="straw", flammable=True,
            built=True, style="thatch", tool="axe")
ROOFTILE = _t(26, "rooftile", "Ziegel", "roof tile", (164, 66, 48), hardness=1.2, drop="rooftile", built=True,
              style="scales")
SLATE = _t(27, "slate", "Schiefer", "slate", (70, 78, 92), hardness=1.4, drop="slate", built=True, style="scales")
PALISADE = _t(28, "palisade", "Palisade", "palisade", (110, 80, 50), hardness=2.0, drop="wood", flammable=True,
              built=True, style="palisade", tool="axe")
DOOR = _t(29, "door", "Tür", "door", (120, 80, 46), hardness=1.0, drop="door", flammable=True, built=True,
          style="door", tool="axe")
DOOR_OPEN = _t(30, "door_open", "Tür", "door (open)", (120, 80, 46), solid=False, hardness=1.0, drop="door",
               flammable=True, built=True, style="door_open", tool="axe")
GATE = _t(31, "gate", "Tor", "gate", (92, 64, 40), hardness=8.0, drop="planks", flammable=True, built=True,
          style="gate", tool="axe")
LADDER = _t(32, "ladder", "Leiter", "ladder", (140, 100, 60), solid=False, hardness=0.4, drop="ladder",
            climbable=True, flammable=True, style="ladder", tool="axe")
PLATFORM = _t(33, "platform", "Steg", "plank walk", (150, 108, 64), solid=False, platform=True, hardness=0.4,
              drop="platform", flammable=True, built=True, style="platform", tool="axe")
TORCH = _t(34, "torch", "Fackel", "torch", (255, 180, 60), solid=False, hardness=0.05, drop="torch", light=1.0,
           style="torch", deco=True)
FARMLAND = _t(35, "farmland", "Acker", "field", (92, 62, 40), natural=True, hardness=0.5, drop="dirt",
              style="farmland")
WHEAT1 = _t(36, "wheat1", "Saat", "seedling", (90, 150, 60), solid=False, hardness=0.05, drop="seeds",
            style="crop", deco=True, extra={"stage": 1})
WHEAT2 = _t(37, "wheat2", "Weizen", "young wheat", (110, 160, 60), solid=False, hardness=0.05, drop="seeds",
            style="crop", deco=True, extra={"stage": 2})
WHEAT3 = _t(38, "wheat3", "Weizen", "green wheat", (150, 170, 70), solid=False, hardness=0.05, drop="seeds",
            style="crop", deco=True, extra={"stage": 3})
WHEAT4 = _t(39, "wheat4", "Weizen", "ripe wheat", (222, 190, 84), solid=False, hardness=0.05, drop="wheat",
            style="crop", deco=True, extra={"stage": 4})
SEAWEED = _t(40, "seaweed", "Seegras", "seaweed", (50, 110, 70), solid=False, hardness=0.05, drop="seaweed",
             style="seaweed", deco=True)
SHELL = _t(41, "shell", "Muschel", "shell", (230, 200, 190), solid=False, hardness=0.05, drop="shell",
           style="shell", deco=True)
FLOWER = _t(42, "flower", "Blume", "flower", (220, 80, 90), solid=False, hardness=0.05, drop="herb",
            style="flower", deco=True)
TALLGRASS = _t(43, "tallgrass", "Halme", "tall grass", (100, 150, 60), solid=False, hardness=0.05, drop="seeds",
               style="tallgrass", deco=True, flammable=True)
BUSH = _t(44, "bush", "Beerenstrauch", "berry bush", (60, 100, 50), solid=False, hardness=0.2, drop="berries",
          style="bush", deco=True, flammable=True)
MUSHROOM = _t(45, "mushroom", "Pilz", "mushroom", (190, 80, 60), solid=False, hardness=0.05, drop="mushroom",
              style="mushroom", deco=True, light=0.15)
VINE = _t(46, "vine", "Weinrebe", "grapevine", (80, 110, 60), solid=False, hardness=0.1, drop="grapes",
          style="vine", deco=True)
OBSIDIAN = _t(47, "obsidian", "Obsidian", "obsidian", (34, 24, 48), natural=True, hardness=5.0, drop="obsidian")
HAY = _t(48, "hay", "Heu", "hay", (210, 184, 96), hardness=0.3, drop="hay", flammable=True, built=True,
         style="thatch")
COBBLE = _t(49, "cobble", "Pflaster", "cobblestone", (128, 124, 116), hardness=2.0, drop="stone", built=True,
            style="cobble")
WORKBENCH = _t(50, "workbench", "Werkbank", "workbench", (140, 96, 56), solid=False, hardness=0.6,
               drop="workbench", style="workbench", deco=True, flammable=True)
ANVIL = _t(51, "anvil", "Amboss", "anvil", (60, 60, 66), solid=False, hardness=2.0, drop="anvil", style="anvil",
           deco=True)
FORGE = _t(52, "forge", "Esse", "forge", (90, 60, 50), solid=False, hardness=2.0, drop="forge", style="forge",
           deco=True, light=0.8)
BED = _t(53, "bed", "Bett", "bed", (170, 60, 50), solid=False, hardness=0.5, drop="bed", style="bed", deco=True)
CHEST = _t(54, "chest", "Truhe", "chest", (120, 80, 40), solid=False, hardness=0.6, drop="chest", style="chest",
           deco=True)
TABLE = _t(55, "table", "Tisch", "table", (130, 90, 52), solid=False, hardness=0.5, drop="table", style="table",
           deco=True, platform=True)
BARREL = _t(56, "barrel", "Fass", "barrel", (110, 74, 40), solid=False, hardness=0.5, drop="barrel",
            style="barrel", deco=True)
THRONE = _t(57, "throne", "Thron", "throne", (180, 140, 40), solid=False, hardness=3.0, drop=None,
            style="throne", deco=True)
BANNER = _t(58, "banner", "Banner", "banner", (170, 30, 30), solid=False, hardness=0.3, drop=None,
            style="banner", deco=True)
ALTAR = _t(59, "altar", "Altar", "altar", (220, 214, 200), solid=False, hardness=3.0, drop=None, style="altar",
           deco=True, light=0.3)
OVEN = _t(60, "oven", "Ofen", "oven", (150, 90, 70), solid=False, hardness=2.0, drop="oven", style="oven",
          deco=True, light=0.5)
STALL = _t(61, "stall", "Marktstand", "market stall", (180, 60, 50), solid=False, hardness=0.5, drop=None,
           style="stall", deco=True)
SIGN = _t(62, "sign", "Wegweiser", "signpost", (120, 86, 50), solid=False, hardness=0.4, drop="planks",
          style="sign", deco=True)
WELL = _t(63, "well", "Brunnen", "well", (130, 126, 120), solid=False, hardness=3.0, drop=None, style="well",
          deco=True)
SAPLING = _t(64, "sapling", "Setzling", "sapling", (90, 140, 60), solid=False, hardness=0.05, drop="sapling",
             style="sapling", deco=True)
DEADGRASS = _t(65, "deadgrass", "Ödgras", "dead grass", (112, 78, 52), natural=True, hardness=0.5, drop="dirt",
               style="grass", color2=(132, 128, 96))
BELL = _t(66, "bell", "Glocke", "bell", (196, 150, 60), solid=False, hardness=3.0, drop=None, style="bell",
          deco=True)
LOOM = _t(67, "loom", "Webstuhl", "loom", (130, 96, 60), solid=False, hardness=0.6, drop="loom", style="loom",
          deco=True)
SANDSTONE = _t(68, "sandstone", "Sandstein", "sandstone", (196, 160, 110), natural=True, hardness=1.4,
               drop="stone")
FLOATROCK = _t(69, "floatrock", "Schwebestein", "float stone", (150, 140, 170), natural=True, hardness=2.0,
               drop="floatstone", style="crystal", light=0.2)
WRECK = _t(70, "wreck", "Wrackholz", "wreck wood", (80, 66, 50), hardness=0.8, drop="planks", built=False,
           style="planks")
GATE_OPEN = _t(71, "gate_open", "Tor", "open gate", (92, 64, 40), solid=False, hardness=8.0, drop="planks",
               flammable=True, built=True, style="gate_open", tool="axe")
FIRE_PIT = _t(72, "campfire", "Lagerfeuer", "campfire", (255, 140, 50), solid=False, hardness=0.3, drop="wood",
              style="campfire", deco=True, light=1.0)
BRIDGE = _t(73, "drawbridge", "Zugbrücke", "drawbridge", (128, 90, 54), hardness=6.0, drop="planks", flammable=True,
            built=True, style="planks", tool="axe")
BRIDGE_UP = _t(74, "drawbridge_up", "Zugbrücke", "raised drawbridge", (118, 82, 48), hardness=6.0, drop="planks",
               flammable=True, built=True, style="gate", tool="axe")
PORTCULLIS = _t(75, "portcullis", "Fallgatter", "portcullis", (70, 70, 76), hardness=14.0, drop="iron_ingot",
                built=True, style="portcullis")
PORTCULLIS_UP = _t(76, "portcullis_up", "Fallgatter", "raised portcullis", (70, 70, 76), solid=False,
                   hardness=14.0, drop="iron_ingot", built=True, style="portcullis_up", deco=True)
PECHNASE = _t(77, "pechnase", "Pechnase", "machicolation", (140, 136, 126), hardness=4.0, drop="brick", built=True,
              style="pechnase")
PROP = _t(78, "prop", "Stütze", "mine prop", (124, 86, 48), hardness=1.0, drop="stuetze", flammable=True, built=True,
          style="prop", tool="axe")
WINCH = _t(79, "winch", "Winde", "winch", (110, 80, 50), solid=False, hardness=2.0, drop="planks", style="winch",
           deco=True)
SULFUR = _t(80, "sulfur", "Schwefel", "sulphur", (118, 116, 112), natural=True, hardness=1.4, drop="schwefel",
            style="ore", color2=(230, 214, 60))
SALPETER = _t(81, "salpeter", "Salpeter", "saltpetre", (112, 90, 70), natural=True, hardness=0.8, drop="salpeter",
              style="crystal")
LOGWALL = _t(82, "logwall", "Blockwand", "log wall", (118, 82, 50), hardness=1.6, drop="wood", flammable=True,
             built=True, style="logwall", tool="axe")
TURF = _t(83, "turf", "Grassode", "turf roof", (92, 72, 50), hardness=0.6, drop="dirt", built=True, style="grass",
          color2=(96, 132, 64))
BASALTBRICK = _t(84, "basaltbrick", "Basaltquader", "basalt block", (66, 62, 66), hardness=3.5, drop="stone",
                 built=True, style="brick")
CHAIN = _t(85, "chain", "Kette", "chain", (70, 70, 76), solid=False, hardness=2.0, drop="iron_ingot", style="chain",
           deco=True)
FERN = _t(86, "fern", "Farn", "fern", (56, 120, 60), solid=False, hardness=0.05, drop="herb", style="fern", deco=True,
          flammable=True)
REED = _t(87, "reed", "Schilf", "reeds", (130, 140, 80), solid=False, hardness=0.05, drop="straw", style="reed",
          deco=True, flammable=True)
HEATHER = _t(88, "heather", "Heide", "heather", (150, 90, 140), solid=False, hardness=0.05, drop="herb",
             style="heather", deco=True, flammable=True)
BIRCH = _t(89, "birch", "Birke", "birch trunk", (226, 222, 210), solid=False, hardness=1.0, drop="wood",
           flammable=True, style="birch", tool="axe")
RYE1 = _t(90, "rye1", "Roggen", "young rye", (90, 150, 70), solid=False, hardness=0.05, drop="seeds_rye",
          style="crop", deco=True, extra={"stage": 1, "crop": "rye"})
RYE2 = _t(91, "rye2", "Roggen", "rye", (110, 156, 70), solid=False, hardness=0.05, drop="seeds_rye", style="crop",
          deco=True, extra={"stage": 2, "crop": "rye"})
RYE3 = _t(92, "rye3", "Roggen", "rye", (160, 166, 90), solid=False, hardness=0.05, drop="seeds_rye", style="crop",
          deco=True, extra={"stage": 3, "crop": "rye"})
RYE4 = _t(93, "rye4", "Roggen", "ripe rye", (196, 170, 110), solid=False, hardness=0.05, drop="rye", style="crop",
          deco=True, extra={"stage": 4, "crop": "rye"})
OAT1 = _t(94, "oat1", "Hafer", "young oats", (100, 160, 70), solid=False, hardness=0.05, drop="seeds_oat",
          style="crop", deco=True, extra={"stage": 1, "crop": "oat"})
OAT2 = _t(95, "oat2", "Hafer", "oats", (120, 166, 80), solid=False, hardness=0.05, drop="seeds_oat", style="crop",
          deco=True, extra={"stage": 2, "crop": "oat"})
OAT3 = _t(96, "oat3", "Hafer", "oats", (170, 180, 110), solid=False, hardness=0.05, drop="seeds_oat", style="crop",
          deco=True, extra={"stage": 3, "crop": "oat"})
OAT4 = _t(97, "oat4", "Hafer", "ripe oats", (220, 210, 150), solid=False, hardness=0.05, drop="oats", style="crop",
          deco=True, extra={"stage": 4, "crop": "oat"})
FLAX1 = _t(98, "flax1", "Flachs", "young flax", (90, 150, 90), solid=False, hardness=0.05, drop="seeds_flax",
           style="crop", deco=True, extra={"stage": 1, "crop": "flax"})
FLAX2 = _t(99, "flax2", "Flachs", "flax", (100, 160, 100), solid=False, hardness=0.05, drop="seeds_flax",
           style="crop", deco=True, extra={"stage": 2, "crop": "flax"})
FLAX3 = _t(100, "flax3", "Flachs", "flowering flax", (120, 150, 210), solid=False, hardness=0.05, drop="seeds_flax",
           style="crop", deco=True, extra={"stage": 3, "crop": "flax"})
FLAX4 = _t(101, "flax4", "Flachs", "ripe flax", (190, 170, 110), solid=False, hardness=0.05, drop="flax",
           style="crop", deco=True, extra={"stage": 4, "crop": "flax"})
TURNIP1 = _t(102, "turnip1", "Rübe", "turnip sprout", (90, 150, 70), solid=False, hardness=0.05, drop="seeds_turnip",
             style="crop", deco=True, extra={"stage": 1, "crop": "turnip"})
TURNIP2 = _t(103, "turnip2", "Rübe", "turnip", (80, 140, 70), solid=False, hardness=0.05, drop="seeds_turnip",
             style="crop", deco=True, extra={"stage": 2, "crop": "turnip"})
TURNIP3 = _t(104, "turnip3", "Rübe", "turnip", (70, 130, 70), solid=False, hardness=0.05, drop="seeds_turnip",
             style="crop", deco=True, extra={"stage": 3, "crop": "turnip"})
TURNIP4 = _t(105, "turnip4", "Rübe", "ripe turnips", (60, 120, 60), solid=False, hardness=0.05, drop="turnip",
             style="crop", deco=True, extra={"stage": 4, "crop": "turnip"})
BOULDER = _t(106, "boulder", "Findling", "boulder", (128, 126, 120), natural=True, hardness=3.0, drop="stone",
             style="noise")

N = 256
SOLID = np.zeros(N, dtype=bool)
NATURAL = np.zeros(N, dtype=bool)
PLATFORM_T = np.zeros(N, dtype=bool)
CLIMB = np.zeros(N, dtype=bool)
FLAMMABLE = np.zeros(N, dtype=bool)
LIGHT = np.zeros(N, dtype=np.float32)
FALLS = np.zeros(N, dtype=bool)
BUILT = np.zeros(N, dtype=bool)
OPAQUE = np.zeros(N, dtype=bool)   # blocks light like a solid
for _t_ in TILES.values():
    SOLID[_t_.id] = _t_.solid
    NATURAL[_t_.id] = _t_.natural
    PLATFORM_T[_t_.id] = _t_.platform
    CLIMB[_t_.id] = _t_.climbable
    FLAMMABLE[_t_.id] = _t_.flammable
    LIGHT[_t_.id] = _t_.light
    FALLS[_t_.id] = _t_.falls
    BUILT[_t_.id] = _t_.built
    OPAQUE[_t_.id] = _t_.solid
# a few non-solid tiles still shade
OPAQUE[LOG.id] = False

CROP_STAGES = [WHEAT1.id, WHEAT2.id, WHEAT3.id, WHEAT4.id]
CROPS = {
    "wheat": [WHEAT1.id, WHEAT2.id, WHEAT3.id, WHEAT4.id],
    "rye": [RYE1.id, RYE2.id, RYE3.id, RYE4.id],
    "oat": [OAT1.id, OAT2.id, OAT3.id, OAT4.id],
    "flax": [FLAX1.id, FLAX2.id, FLAX3.id, FLAX4.id],
    "turnip": [TURNIP1.id, TURNIP2.id, TURNIP3.id, TURNIP4.id],
}
CROP_OF = {tid: (crop, i) for crop, ids in CROPS.items() for i, tid in enumerate(ids)}
RIPE = {ids[3] for ids in CROPS.values()}
# which seasons each crop grows in (0 spring .. 3 winter): rye is the winter grain of medieval Germany
CROP_SEASONS = {"wheat": (0, 1), "rye": (2, 3, 0), "oat": (0, 1), "flax": (0, 1), "turnip": (1, 2)}

# Background walls (separate layer)
BG = {
    0: ("none", None),
    1: ("dirt", (62, 44, 32)),
    2: ("stone", (64, 62, 62)),
    3: ("planks", (98, 70, 44)),
    4: ("fachwerk", (176, 166, 144)),
    5: ("brick", (92, 90, 86)),
    6: ("window", (60, 80, 100)),
    7: ("tapestry", (110, 30, 36)),
    8: ("ash", (46, 40, 40)),
    9: ("snowstone", (120, 128, 140)),
}
BG_DIRT, BG_STONE, BG_PLANKS, BG_FACHWERK, BG_BRICK, BG_WINDOW, BG_TAPESTRY, BG_ASH, BG_SNOWSTONE = range(1, 10)
