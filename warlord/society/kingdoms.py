"""The seven realms. Their rulers are the seven Kurfürsten (prince-electors) who elect the king.

Positions are fractions of world width so any world size keeps the same geography:
    Abyss | Randmark | Waldheim | Hochburg | Heiligenstein | Lübenau | ~~ Graues Meer ~~ | Frostholm | ~ | Glutmark | Lava
"""

KINGDOMS = [
    dict(key="randmark", de="Grafschaft Randmark", en="County of the Edge-March", span=(0.005, 0.115),
         realm="Grafschaft", ruler_rank=6, ruler="Graf Randolf", colors=((96, 100, 122), (230, 228, 220)),
         charge="tower",
         blurb="A poor county of rye and sheep on the brink of the Abyss. The land here is said to crumble each "
               "winter.",
         settlements=[("village", "Erlenbach"), ("hamlet", "Kargenhof"), ("castle", "Burg Randeck"),
                      ("village", "Grauweiler")]),
    dict(key="waldheim", de="Herzogtum Waldheim", en="Duchy of Forest-Home", span=(0.115, 0.271),
         realm="Herzogtum", ruler_rank=7, ruler="Herzog Eberhard", colors=((40, 96, 54), (214, 178, 74)),
         charge="tree",
         blurb="Endless oak and fir. Charcoal burners, hunters, and robber knights who hide in the deep wood.",
         settlements=[("village", "Tannfeld"), ("robber", "Schwarzfels"), ("town", "Eichenau"),
                      ("village", "Moosbach"), ("castle", "Burg Waldheim"), ("village", "Fennhausen")]),
    dict(key="hochburg", de="Königreich Hochburg", en="Kingdom of High-Castle", span=(0.271, 0.5),
         realm="Königreich", ruler_rank=8, ruler="König Albrecht", colors=((30, 28, 30), (214, 178, 74)),
         charge="eagle",
         blurb="The largest realm: mountains full of silver, and the crag-castle of the old kings.",
         settlements=[("village", "Steinach"), ("town", "Bergheim"), ("mine", "Silberberg"),
                      ("capital", "Hochburg"), ("village", "Felsdorf"), ("castle", "Adlerhorst"),
                      ("town", "Talheim")]),
    dict(key="heiligenstein", de="Fürstbistum Heiligenstein", en="Prince-Bishopric of Holy-Stone",
         span=(0.5, 0.594), realm="Fürstbistum", ruler_rank=8, ruler="Fürstbischof Wolfram",
         colors=((236, 232, 222), (170, 30, 34)), charge="cross",
         blurb="A church state of vineyards and monasteries. The Bishop is both priest and prince.",
         settlements=[("village", "Weinsberg"), ("monastery", "Kloster Lichtenau"), ("town", "Heiligenstein")]),
    dict(key="luebenau", de="Freie Reichsstadt Lübenau", en="Free Imperial City of Lübenau", span=(0.594, 0.667),
         realm="Reichsstadt", ruler_rank=6, ruler="Bürgermeister Hinrich Witte",
         colors=((176, 34, 36), (236, 232, 222)), charge="ship",
         blurb="Merchants answer to no lord here. 'Stadtluft macht frei' — city air makes you free.",
         settlements=[("village", "Deichdorf"), ("city", "Lübenau"), ("port", "Lübenau Hafen")]),
    dict(key="frostholm", de="Inselkönigreich Frostholm", en="Island Kingdom of Frost-Isle", span=(0.781, 0.865),
         realm="Königreich", ruler_rank=8, ruler="Königin Sigrun", colors=((40, 70, 140), (236, 236, 240)),
         charge="star",
         blurb="Across the Grey Sea: fjords, snow and a queen who keeps the oldest chronicles of the world.",
         settlements=[("port", "Eisvik"), ("village", "Wolfsheim"), ("capital", "Frostholm")]),
    dict(key="glutmark", de="Markgrafschaft Glutmark", en="Margraviate of the Ember-March", span=(0.885, 0.99),
         realm="Markgrafschaft", ruler_rank=7, ruler="Markgraf Otto der Rote", colors=((170, 64, 24), (30, 26, 24)),
         charge="flame",
         blurb="Ash, basalt and the glow of the Fire Sea. Its smiths forge the finest steel from Glutstein.",
         settlements=[("port", "Brandhafen"), ("village", "Aschenfeld"), ("castle", "Glutburg"),
                      ("village", "Schlackental")]),
]

BY_KEY = {k["key"]: k for k in KINGDOMS}

# Biome bands (fractions of width). Order west -> east.
BIOMES = [
    (0.0, 0.0052, "abyss"),
    (0.0052, 0.03, "edge"),
    (0.03, 0.115, "plains"),
    (0.115, 0.21, "forest"),
    (0.21, 0.24, "moor"),
    (0.24, 0.271, "forest"),
    (0.271, 0.30, "hills"),
    (0.30, 0.47, "mountains"),
    (0.47, 0.5, "hills"),
    (0.5, 0.594, "vineyard"),
    (0.594, 0.635, "plains"),
    (0.635, 0.667, "coast"),
    (0.667, 0.715, "ocean"),
    (0.715, 0.727, "islet"),
    (0.727, 0.781, "ocean"),
    (0.781, 0.865, "snow"),
    (0.865, 0.885, "ocean"),
    (0.885, 0.95, "ashland"),
    (0.95, 0.99, "volcanic"),
    (0.99, 1.0, "lavasea"),
]

BIOME_NAMES = {
    "abyss": ("Der Abgrund", "the Abyss"), "edge": ("Ödland", "wasteland"), "plains": ("Wiesen", "meadows"),
    "forest": ("Wald", "forest"), "moor": ("Moor", "bog"), "hills": ("Hügel", "hills"),
    "mountains": ("Gebirge", "mountains"), "vineyard": ("Weinberge", "vineyards"), "coast": ("Küste", "coast"),
    "ocean": ("Das Graue Meer", "the Grey Sea"), "islet": ("Möweninsel", "Gull Isle"),
    "snow": ("Schneeland", "snowland"), "ashland": ("Aschland", "ashland"), "volcanic": ("Vulkane", "volcanoes"),
    "lavasea": ("Das Glutmeer", "the Fire Sea"),
}

# Diplomatic starting state: pairs at war (they will evolve during play)
INITIAL_WARS = [("glutmark", "frostholm"), ("waldheim", "randmark")]
