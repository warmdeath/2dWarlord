"""Recipes. Stations must be within reach: Werkbank, Amboss+Esse, Ofen, Webstuhl."""
from dataclasses import dataclass



@dataclass
class Recipe:
    out: str
    n: int
    needs: dict
    station: str = None   # None / workbench / smithy / oven / loom / campfire


# which fittings count as which workshop
STATION_DECOR = {
    "workbench": ("workbench", "table"),
    "smithy": ("anvil",),
    "oven": ("oven", "forge"),
    "loom": ("loom",),
    "campfire": ("campfire", "hearth", "forge", "oven"),
}

RECIPES = [
    Recipe("verband", 3, {"cloth": 1}),
    Recipe("stuetze", 3, {"wood": 2}, "workbench"),
    Recipe("pech", 2, {"wood": 3, "coal": 1}, "oven"),
    Recipe("kugel", 2, {"stone": 6}, "workbench"),
    Recipe("pulver", 1, {"salpeter": 3, "schwefel": 1, "coal": 1}, "workbench"),
    Recipe("verband", 1, {"wool": 1, "herb": 1}),
    Recipe("workbench", 1, {"planks": 8}),
    Recipe("torch", 4, {"wood": 1, "coal": 1}),
    Recipe("torch", 2, {"wood": 2}),
    Recipe("campfire", 1, {"wood": 5, "stone": 3}),
    Recipe("knueppel", 1, {"wood": 3}),
    Recipe("chest", 1, {"planks": 8, "iron_ingot": 1}, "workbench"),
    Recipe("table", 1, {"planks": 6}, "workbench"),
    Recipe("bed", 1, {"planks": 6, "wool": 4}, "workbench"),
    Recipe("barrel", 1, {"planks": 5}, "workbench"),
    Recipe("fachwerk", 4, {"planks": 2, "clay": 2}, "workbench"),
    Recipe("straw", 4, {"wheat": 2}),
    Recipe("mistgabel", 1, {"shaft": 1, "iron_ingot": 1}, "smithy"),
    Recipe("flegel", 1, {"wood": 5, "rope": 1}, "workbench"),
    Recipe("bogen", 1, {"shaft": 1, "rope": 2}, "workbench"),
    Recipe("arrow", 10, {"wood": 2, "stone": 1}, "workbench"),
    Recipe("fire_arrow", 5, {"arrow": 5, "coal": 1, "straw": 1}, "workbench"),
    Recipe("holzschild", 1, {"planks": 6, "leather": 1}, "workbench"),
    Recipe("speer", 1, {"shaft": 1, "iron_ingot": 1}, "smithy"),
    Recipe("loom", 1, {"planks": 10, "rope": 2}, "workbench"),
    Recipe("rope", 2, {"wheat": 3}, "workbench"),
    Recipe("brick", 4, {"stone": 4}, "workbench"),
    Recipe("oven", 1, {"stone": 20, "clay": 6}, "workbench"),
    Recipe("forge", 1, {"stone": 20, "coal": 4}, "workbench"),
    Recipe("anvil", 1, {"iron_ingot": 6}, "workbench"),
    Recipe("rooftile", 6, {"clay": 3}, "oven"),
    Recipe("iron_ingot", 1, {"iron_ore": 2, "coal": 1}, "oven"),
    Recipe("silver_coin", 30, {"silver_ore": 2, "coal": 1}, "oven"),
    Recipe("flour", 1, {"wheat": 3}, "workbench"),
    Recipe("flour", 1, {"rye": 3}, "workbench"),
    Recipe("cloth", 1, {"flax": 3}, "loom"),
    Recipe("hacke", 1, {"wood": 2, "iron_ingot": 1}, "smithy"),
    Recipe("pflug", 1, {"wood": 8, "iron_ingot": 3, "rope": 2}, "smithy"),
    Recipe("bread", 2, {"flour": 1}, "oven"),
    Recipe("fish", 1, {"fish": 1}, "campfire"),
    Recipe("cloth", 1, {"wool": 3}, "loom"),
    Recipe("gambeson", 1, {"cloth": 6, "wool": 4}, "loom"),
    Recipe("spitzhacke", 1, {"wood": 2, "iron_ingot": 2}, "smithy"),
    Recipe("hammer", 1, {"wood": 2, "iron_ingot": 1}, "smithy"),
    Recipe("sichel", 1, {"wood": 1, "iron_ingot": 1}, "smithy"),
    Recipe("axt", 1, {"handle": 1, "iron_ingot": 2}, "smithy"),
    Recipe("dolch", 1, {"iron_ingot": 1, "leather": 1}, "smithy"),
    Recipe("schwert", 1, {"iron_ingot": 3, "leather": 1}, "smithy"),
    Recipe("langschwert", 1, {"iron_ingot": 5, "leather": 1}, "smithy"),
    Recipe("streitkolben", 1, {"iron_ingot": 4, "wood": 1}, "smithy"),
    Recipe("spiess", 1, {"wood": 6, "iron_ingot": 1}, "smithy"),
    Recipe("hellebarde", 1, {"wood": 4, "iron_ingot": 4}, "smithy"),
    Recipe("lanze", 1, {"wood": 6, "iron_ingot": 2}, "smithy"),
    Recipe("armbrust", 1, {"wood": 4, "iron_ingot": 3, "rope": 2}, "smithy"),
    Recipe("bolt", 8, {"wood": 1, "iron_ingot": 1}, "smithy"),
    Recipe("dreieckschild", 1, {"planks": 6, "iron_ingot": 1, "leather": 2}, "smithy"),
    Recipe("pavese", 1, {"planks": 12, "iron_ingot": 2, "leather": 2}, "smithy"),
    Recipe("kettenhaube", 1, {"iron_ingot": 3}, "smithy"),
    Recipe("eisenhut", 1, {"iron_ingot": 4}, "smithy"),
    Recipe("kettenhemd", 1, {"iron_ingot": 10, "leather": 2}, "smithy"),
    Recipe("beckenhaube", 1, {"iron_ingot": 6, "glutstein": 1}, "smithy"),
    Recipe("topfhelm", 1, {"iron_ingot": 8}, "smithy"),
    Recipe("plattenrock", 1, {"iron_ingot": 16, "leather": 4, "glutstein": 2}, "smithy"),
]


def stations_near(world, tx, ty, radius=4):
    """Workshops within a few steps: fittings of buildings and stations you placed yourself."""
    px = tx * 16 + 8
    found = set()
    r = radius * 16 + 24
    for d in world.near("decor_chunks", px - r, px + r):
        if abs(d.x - px) < r and not d.gone:
            for st, kinds in STATION_DECOR.items():
                if d.kind in kinds:
                    found.add(st)
    for o in world.objects:
        if abs(o.x - px) < r and o.shape_key:
            for st, kinds in STATION_DECOR.items():
                if o.shape_key in kinds:
                    found.add(st)
    return found


def available(inv, stations):
    out = []
    for r in RECIPES:
        ok_station = r.station is None or r.station in stations
        out.append((r, ok_station and inv.has(r.needs), ok_station))
    return out
