"""Building materials: how they look, how hard they are, whether they burn, what they leave behind."""
from dataclasses import dataclass


@dataclass
class Mat:
    key: str
    de: str
    en: str
    color: tuple
    edge: tuple
    hp: float           # hit points per 100 px² of piece area
    flammable: bool
    density: float      # mass per px²
    drop: str = None    # item left behind when broken
    hard: float = 1.0   # how well it shrugs off blunt and cutting blows (weapons vs walls)
    detail: str = None  # drawing style
    sound: str = "hit_wood"


MATS = {}


def _m(key, de, en, color, edge, hp, flammable, density, drop=None, hard=1.0, detail=None, sound="hit_wood"):
    MATS[key] = Mat(key, de, en, color, edge, hp, flammable, density, drop, hard, detail, sound)


_m("timber", "Balken", "beam", (92, 62, 40), (54, 36, 24), 3.0, True, 0.010, "wood", 1.0, "grain")
_m("plank", "Bretter", "planks", (150, 108, 66), (92, 64, 40), 2.2, True, 0.008, "planks", 0.8, "boards")
_m("plaster", "Lehmputz", "daub", (222, 208, 176), (170, 150, 120), 1.2, False, 0.012, "clay", 0.5, None)
_m("wattle", "Flechtwerk", "wattle", (150, 118, 76), (96, 72, 46), 1.0, True, 0.006, "wood", 0.4, "weave")
_m("stone", "Bruchstein", "rubble stone", (148, 144, 134), (96, 92, 86), 7.0, False, 0.030, "stone", 2.2,
   "rough", "hit_stone")
_m("ashlar", "Quader", "ashlar", (178, 164, 136), (120, 108, 88), 9.0, False, 0.030, "brick", 2.6, "ashlar",
   "hit_stone")
_m("redstone", "Buntsandstein", "red sandstone", (166, 96, 78), (110, 60, 48), 8.0, False, 0.030, "brick", 2.4,
   "ashlar", "hit_stone")
_m("brick", "Backstein", "brick", (164, 72, 52), (108, 44, 34), 6.0, False, 0.026, "brick", 2.0, "bricks",
   "hit_stone")
_m("basalt", "Basalt", "basalt", (64, 62, 68), (36, 34, 40), 11.0, False, 0.034, "stone", 3.0, "ashlar",
   "hit_stone")
_m("thatch", "Stroh", "thatch", (198, 162, 86), (140, 108, 52), 1.4, True, 0.004, "straw", 0.3, "thatch")
_m("rooftile", "Ziegel", "roof tiles", (172, 76, 52), (112, 46, 32), 2.0, False, 0.014, "rooftile", 1.2, "tiles",
   "hit_stone")
_m("slate", "Schiefer", "slate", (72, 78, 94), (44, 48, 60), 2.6, False, 0.016, "slate", 1.4, "slates",
   "hit_stone")
_m("shingle", "Schindeln", "shingles", (118, 86, 56), (76, 54, 34), 1.8, True, 0.006, "wood", 0.8, "slates")
_m("turf", "Grassoden", "turf", (96, 122, 62), (60, 82, 40), 2.4, False, 0.016, "dirt", 0.6, "turf")
_m("log", "Rundholz", "log", (124, 88, 54), (74, 52, 32), 4.0, True, 0.010, "wood", 1.2, "logs")
_m("iron", "Eisen", "iron", (84, 86, 94), (40, 42, 48), 25.0, False, 0.060, "iron_bar", 4.0, "rivets",
   "hit_metal")
_m("earth", "Erde", "earth", (122, 92, 62), (84, 62, 42), 3.0, False, 0.020, "dirt", 0.5, None, "hit_dirt")
_m("cobble", "Pflaster", "cobbles", (128, 124, 116), (84, 80, 76), 8.0, False, 0.030, "stone", 2.0, "rough",
   "hit_stone")
_m("glass", "Butzenglas", "crown glass", (150, 180, 170), (70, 90, 88), 0.4, False, 0.010, None, 0.2, "panes",
   "hit_stone")
_m("cloth", "Tuch", "cloth", (170, 60, 50), (110, 36, 30), 0.6, True, 0.002, None, 0.1, None)
_m("bone", "Knochen", "bone", (220, 214, 196), (150, 144, 128), 2.0, False, 0.010, None, 0.8, None)
_m("rock", "Fels", "rock", (112, 108, 104), (70, 68, 66), 14.0, False, 0.034, "stone", 3.0, "rough",
   "hit_stone")

MASONRY = {"stone", "ashlar", "redstone", "brick", "basalt", "cobble", "rock"}
TIMBER = {"timber", "plank", "log", "shingle", "wattle"}
