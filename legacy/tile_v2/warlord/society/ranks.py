"""Die Ständeordnung — the social ladder of 1300.

Each rank exists for a reason: how much land (Lehen / fief) a person holds, what they do,
and what they owe to whom. Rising means gaining Ehre (honour), wealth and a liege who grants land.
"""
from dataclasses import dataclass


@dataclass
class Rank:
    level: int
    key: str
    de: str
    en: str
    estate: str          # Bauernstand / Bürgerstand / Adel / Klerus
    fief: str            # what land they hold
    duty: str            # what they owe
    privilege: str       # what they may do
    why: str             # the reason this rank exists
    address_de: str      # how others address them
    address_en: str
    du: bool             # addressed with informal 'du' (True) or formal 'Ihr' (False)
    command: int         # soldiers they may lead
    honour_needed: int
    money_needed: int


RANKS = [
    Rank(0, "leibeigener", "Leibeigener", "serf", "Bauernstand",
         "none — he tills his lord's land", "Frondienst (labour 3 days a week) and the Zehnt (tithe)",
         "none; may not leave the land or bear a sword in town",
         "Bound to the soil so the manor always has hands. The lord owes him protection in return.",
         "Bursche", "lad", True, 6, 0, 0),
    Rank(1, "freier", "Freier Bauer", "free peasant", "Bauernstand",
         "his own small farm (Hof)", "taxes to the lord and the Zehnt to the church",
         "may travel, marry and sell freely",
         "Bought or won his freedom. 'Stadtluft macht frei' — a year and a day in a city frees a serf.",
         "Bauer", "farmer", True, 8, 5, 0),
    Rank(2, "buerger", "Bürger", "burgher", "Bürgerstand",
         "a house in a town and a place in a guild (Zunft)", "town taxes and guarding the walls",
         "may trade in the market, join a guild, vote in the town",
         "Towns live by trade. Citizenship (Bürgerrecht) is bought and sworn, and makes you nobody's serf.",
         "Meister", "master", False, 12, 15, 60),
    Rank(3, "knappe", "Knappe", "squire", "Adel",
         "none yet — he serves a knight", "serve his knight in war and at court",
         "may bear arms and ride; learns war",
         "Knighthood is learned. Before you lead, you carry the shield of one who does.",
         "junger Herr", "young sir", False, 20, 30, 0),
    Rank(4, "ritter", "Ritter", "knight", "Adel",
         "a Rittergut — one village and its fields", "Heerfolge: 40 days of war service a year with his men",
         "low justice on his manor, may build a fortified house",
         "A knight is paid in land: the village feeds him so he can fight for his liege.",
         "Herr Ritter", "Sir Knight", False, 40, 60, 0),
    Rank(5, "freiherr", "Freiherr", "baron", "Adel",
         "several villages (3+)", "provides a company of knights and foot to his count",
         "low justice over all his villages, may build a castle with leave",
         "More land means more men to arm — and the duty to lead them.",
         "Euer Gnaden", "Your Grace", False, 80, 120, 300),
    Rank(6, "graf", "Graf", "count", "Adel",
         "a county (Grafschaft): a castle, towns and villages", "keeps the peace and judges in the king's name",
         "high justice (Blutgericht), may mint coin with leave, raises armies",
         "A count governs a whole district for his duke or king.",
         "Herr Graf", "My Lord Count", False, 160, 220, 800),
    Rank(7, "herzog", "Herzog", "duke", "Adel",
         "a duchy of many counties", "leads the host of a whole land",
         "makes laws, grants fiefs to counts and knights",
         "The duke binds many counts to one banner.",
         "Euer Durchlaucht", "Your Serene Highness", False, 320, 400, 2000),
    Rank(8, "koenig", "König / Kurfürst", "king / prince-elector", "Adel",
         "a realm", "answers only to God — and to the Kaiser, if one is elected",
         "votes in the Königswahl (royal election)",
         "Seven rulers elect the Kaiser. Each is a king in his own land.",
         "Euer Majestät", "Your Majesty", False, 640, 9999, 99999),
]

CLERGY = {
    "moench": ("Mönch", "monk", "Bruder", "Brother"),
    "priester": ("Priester", "priest", "Hochwürden", "Reverend"),
    "abt": ("Abt", "abbot", "Ehrwürdiger Vater", "Reverend Father"),
    "bischof": ("Fürstbischof", "prince-bishop", "Exzellenz", "Your Excellency"),
}


def rank(level):
    return RANKS[max(0, min(len(RANKS) - 1, level))]


def address(level):
    """How an NPC addresses someone of `level`."""
    r = rank(level)
    return r.address_de, r.address_en, r.du
