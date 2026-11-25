"""Troop types. Each has a real tactical role (rock-paper-scissors with nuance)."""
from dataclasses import dataclass


@dataclass
class UnitType:
    key: str
    de: str
    en: str
    weapons: tuple
    shield: str = None
    armor: str = "kleidung"
    helmet: str = None
    quality: float = 0.5
    ranged: str = None       # "arrow" / "bolt"
    cavalry: bool = False
    cost: int = 10           # Pfennig per soldier per muster
    role: str = ""


UNITS = {
    "bauern": UnitType("bauern", "Bauernhaufen", "peasant levy", ("mistgabel", "flegel", "knueppel", "axt"),
                       None, "kleidung", None, 0.28, cost=2,
                       role="Cheap and many. Breaks quickly, but fights hardest at home."),
    "speer": UnitType("speer", "Speerträger", "spearmen", ("speer",), "holzschild", "gambeson", "kettenhaube", 0.55,
                      cost=8, role="Reach + shields. Brace (Igel) against horses."),
    "schild": UnitType("schild", "Schildträger", "sword & shield", ("schwert", "streitkolben", "axt"), "dreieckschild",
                       "kettenhemd", "eisenhut", 0.72, cost=16,
                       role="Best in the Schildwall: shrugs off arrows, holds any line."),
    "spiess": UnitType("spiess", "Spießer", "pikemen", ("spiess",), None, "gambeson", "eisenhut", 0.6, cost=10,
                       role="Three ranks of points. Cavalry dies on them; swordsmen slip inside."),
    "hellebarde": UnitType("hellebarde", "Hellebardiere", "halberdiers", ("hellebarde",), None, "kettenhemd",
                           "beckenhaube", 0.72, cost=18, role="Hook riders down, cleave armour."),
    "bogen": UnitType("bogen", "Bogenschützen", "archers", ("bogen",), None, "gambeson", None, 0.5, "arrow", cost=10,
                      role="Volleys at long range. Wind at their backs doubles their worth."),
    "armbrust": UnitType("armbrust", "Armbrustschützen", "crossbowmen", ("armbrust",), "pavese", "gambeson",
                         "eisenhut", 0.6, "bolt", cost=16, role="Slow, but bolts punch through mail."),
    "reisige": UnitType("reisige", "Reisige", "mounted men-at-arms", ("schwert",), "holzschild", "kettenhemd",
                        "kettenhaube", 0.7, cavalry=True, cost=30, role="Fast. Hunt archers, ride down the routed."),
    "ritter": UnitType("ritter", "Ritter", "knights", ("lanze",), "dreieckschild", "plattenrock", "topfhelm", 0.95,
                       cavalry=True, cost=60, role="The charge that ends battles — unless it meets a hedge of pikes."),
    "leiter": UnitType("leiter", "Leiterträger", "ladder men", ("axt", "schwert", "streitkolben"), "holzschild",
                       "gambeson", "kettenhaube", 0.55, cost=12,
                       role="Carry Sturmleitern: raise them against a wall and climb, one man at a time."),
    "mineure": UnitType("mineure", "Mineure", "sappers", ("spitzhacke",), None, "gambeson", "eisenhut", 0.5, cost=14,
                        role="Dig under a wall, prop it on timber, then burn the props. The wall falls."),
    "raeuber": UnitType("raeuber", "Räuberbande", "robber band", ("axt", "knueppel", "dolch", "schwert"), "holzschild",
                        "gambeson", None, 0.45, cost=0, role="Robber knights' rabble."),
}
