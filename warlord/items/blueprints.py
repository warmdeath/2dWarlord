"""Bauplan — blueprints. Place a ghost, pay the materials, and watch it rise tile by tile."""
from dataclasses import dataclass
from typing import Callable

from ..world import structures as S
from ..world import tiles as T


@dataclass
class Blueprint:
    key: str
    de: str
    en: str
    width: int
    cost: dict
    build: Callable
    rank: int = 0
    note: str = ""


def _hut(w, x, g, rng):
    S.house(w, x, g, width=7, height=4, style="peasant", door_side=1, rng=rng)


def _house(w, x, g, rng):
    S.house(w, x, g, width=10, height=4, style="burgher", door_side=1, rng=rng)


def _stonehouse(w, x, g, rng):
    S.house(w, x, g, width=11, height=5, style="stone", door_side=1, rng=rng)


def _smithy(w, x, g, rng):
    h = S.house(w, x, g, width=9, height=4, style="peasant", door_side=1, rng=rng, kind="smithy")
    S._put(w, h["x0"] + 3, g - 1, T.ANVIL.id)
    S._put(w, h["x0"] + 4, g - 1, T.FORGE.id)


def _palisade(w, x, g, rng):
    for i in range(6):
        S.palisade(w, x + i, g)


def _wall(w, x, g, rng):
    S.wall_tower(w, x, g, height=8, thick=2, gate=False)


def _gate(w, x, g, rng):
    S.wall_tower(w, x, g, height=8, thick=2, gate=True)


def _tower(w, x, g, rng):
    S.tower(w, x, g, width=6, height=14)


def _church(w, x, g, rng):
    S.church(w, x, g, width=13, rng=rng)


def _mill(w, x, g, rng):
    S.windmill(w, x, g)


def _well(w, x, g, rng):
    S.well(w, x, g)


def _field(w, x, g, rng):
    S.field(w, x, x + 9, g, rng)


def _hall(w, x, g, rng):
    S.great_hall(w, x, g, width=17)


def _castle(w, x, g, rng):
    S.castle(w, x, g, rng, size="castle")


BLUEPRINTS = [
    Blueprint("field", "Acker", "field (10 wide)", 10, {"seeds": 6}, _field, 0, "Sow wheat. Ripens in 2-3 days."),
    Blueprint("palisade", "Palisade", "palisade (6 stakes)", 6, {"wood": 12}, _palisade, 0,
              "Cheap wall of sharpened logs. Burns."),
    Blueprint("hut", "Hütte", "peasant hut", 7, {"planks": 20, "straw": 14, "wood": 6}, _hut, 0,
              "Fachwerk walls, thatched roof — a serf's home."),
    Blueprint("well", "Brunnen", "well", 3, {"stone": 12, "planks": 4}, _well, 0, "Water for the village."),
    Blueprint("house", "Bürgerhaus", "burgher house", 10, {"planks": 40, "rooftile": 20, "clay": 10}, _house, 1,
              "Two storeys and a tiled roof."),
    Blueprint("smithy", "Schmiede", "smithy", 9, {"planks": 24, "straw": 16, "iron_ingot": 6, "stone": 20}, _smithy, 1,
              "Anvil and forge: weapons and armour."),
    Blueprint("mill", "Windmühle", "windmill", 5, {"planks": 40, "straw": 10}, _mill, 1, "Turns wheat into flour."),
    Blueprint("wall", "Mauer", "stone wall", 2, {"brick": 30}, _wall, 2, "Two bricks thick, with battlements."),
    Blueprint("gate", "Tor", "gatehouse", 2, {"brick": 24, "planks": 12}, _gate, 2, "A wall with a gate."),
    Blueprint("tower", "Wachturm", "watchtower", 6, {"brick": 70, "planks": 20, "slate": 12}, _tower, 3,
              "See far, shoot far."),
    Blueprint("stonehouse", "Steinhaus", "stone house", 11, {"brick": 60, "slate": 24, "planks": 16}, _stonehouse,
              3, "Will not burn."),
    Blueprint("church", "Kapelle", "chapel", 13, {"brick": 80, "slate": 30, "planks": 20}, _church, 4,
              "A village needs its bell."),
    Blueprint("hall", "Rittersaal", "knight's hall", 17, {"brick": 90, "slate": 40, "planks": 30, "cloth": 6}, _hall,
              4, "Where a lord holds court."),
    Blueprint("castle", "Burg", "castle", 60, {"brick": 500, "slate": 120, "planks": 150, "iron_ingot": 20}, _castle,
              5, "Curtain walls, keep, towers, hall."),
]
