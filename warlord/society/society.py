"""Population, fiefs, markets and politics for the whole world.

Everyone in the world exists as a lightweight Person record. Only people near the player are
'materialised' as full humanoids (level-of-detail simulation), so the 1-hour-wide world can hold
hundreds of named inhabitants without slowing down.
"""
import random
from dataclasses import dataclass, field

from ..settings import TILE
from .kingdoms import KINGDOMS, BY_KEY, INITIAL_WARS
from .names import person_name, make_look
from ..items.items import ITEMS


@dataclass
class Person:
    id: int
    name: str
    job: str
    rank: int
    kingdom: str
    settlement: int
    home_x: float
    work_x: float
    g: int
    look: dict
    female: bool = False
    bed_x: int = None
    field: tuple = None
    patrol: tuple = None
    social_x: float = None
    fighter: bool = False
    noble: bool = False
    clergy: bool = False
    alive: bool = True
    hp: float = 100.0
    gear: tuple = ("fists", "", "kleidung", "")
    title: str = ""
    relation: float = 0.0
    seat: str = None


@dataclass
class Army:
    id: int
    kingdom: str
    x: float
    target: int           # settlement index
    units: list           # [[unit_key, count], ...]
    speed: float = 45.0
    materialized: bool = False
    haufen: list = field(default_factory=list)
    state: str = "march"

    def strength(self):
        from ..combat.units import UNITS
        return sum(c * (0.5 + UNITS[u].quality) * (2.0 if UNITS[u].cavalry else 1.0) for u, c in self.units)


BASE_TARGET = {"wheat": 40, "bread": 30, "flour": 20, "fish": 25, "meat": 20, "beer": 20, "wine": 15, "salt": 15,
               "wood": 60, "planks": 40, "stone": 60, "iron_ore": 20, "iron_ingot": 15, "coal": 25, "cloth": 15,
               "wool": 20, "leather": 15, "rope": 15, "arrow": 80, "torch": 30, "cheese": 15}
SPECIALTY = {
    "randmark": {"wheat": 1.8, "wool": 2.0, "floatstone": 0.5},
    "waldheim": {"wood": 2.5, "planks": 1.8, "leather": 1.5, "meat": 1.5, "coal": 1.8},
    "hochburg": {"iron_ore": 2.5, "iron_ingot": 1.8, "silver_ore": 2.0, "stone": 2.0, "cheese": 1.6},
    "heiligenstein": {"wine": 3.0, "bread": 1.5, "cloth": 1.4},
    "luebenau": {"fish": 2.5, "salt": 3.0, "cloth": 1.8, "rope": 2.0, "beer": 1.8},
    "frostholm": {"fish": 2.5, "leather": 2.2, "meat": 1.6},
    "glutmark": {"glutstein": 3.0, "coal": 2.0, "iron_ingot": 1.4},
}


class Market:
    def __init__(self, kingdom, size, rng):
        self.stock = {}
        mult = SPECIALTY.get(kingdom, {})
        for k, t in BASE_TARGET.items():
            self.stock[k] = int(t * size * mult.get(k, 1.0) * rng.uniform(0.6, 1.2))
        for k, m in mult.items():
            if k not in self.stock:
                self.stock[k] = int(10 * size * m)
        self.size = size

    def target(self, key):
        return BASE_TARGET.get(key, 10) * self.size

    def price(self, key, buying=True):
        base = ITEMS[key].value if key in ITEMS else 1
        s = self.stock.get(key, 0)
        t = self.target(key)
        f = (t / (s + t * 0.25)) ** 0.7
        f = max(0.35, min(3.5, f))
        p = base * f * (1.15 if buying else 0.75)
        return max(1, int(round(p)))

    def daily(self, pop, rng):
        # consumption
        for k, need in (("bread", 0.15), ("wheat", 0.1), ("fish", 0.05), ("beer", 0.05), ("wood", 0.1),
                        ("meat", 0.04)):
            self.stock[k] = max(0, self.stock.get(k, 0) - int(pop * need + rng.random()))
        # baseline production from the countryside
        for k in BASE_TARGET:
            self.stock[k] = self.stock.get(k, 0) + int(self.target(k) * 0.08 * rng.uniform(0.5, 1.3))


class Society:
    def __init__(self, world, seed):
        self.world = world
        self.rng = random.Random(seed + 77)
        self.people = []
        self.by_settlement = {}
        self.markets = {}
        self.wars = set()
        self.relations = {}
        self.armies = []
        self.army_ids = 0
        self.owner = {}      # settlement index -> kingdom key (can change by conquest)
        self.lords = {}      # settlement index -> person id of the fief holder
        self.rulers = {}     # kingdom -> person id
        self.day_done = -1
        self.news = []       # (text, gloss)
        self.wanted = set()  # kingdoms where the player is outlawed
        for a, b in INITIAL_WARS:
            self.wars.add(frozenset((a, b)))
        for k in KINGDOMS:
            for k2 in KINGDOMS:
                if k is not k2:
                    self.relations[(k["key"], k2["key"])] = 0.0
        self._populate()

    # ------------------------------------------------------------------ population
    def _new_person(self, **kw):
        p = Person(id=len(self.people), **kw)
        self.people.append(p)
        self.by_settlement.setdefault(p.settlement, []).append(p.id)
        return p

    def _populate(self):
        rng = self.rng
        for si, s in enumerate(self.world.settlements):
            k = s["kingdom"]
            self.owner[si] = k
            kd = BY_KEY[k]
            colors = kd["colors"]
            g = s["g"]
            size = {"hamlet": 0.4, "village": 0.7, "town": 1.3, "city": 2.0, "capital": 2.5, "castle": 0.6,
                    "robber": 0.3, "monastery": 0.5, "port": 0.9, "mine": 0.6}[s["type"]]
            self.markets[si] = Market(k, size, rng)
            fields = [b for b in s["buildings"] if b["kind"] == "field"]
            center = (s["x0"] + s["x1"]) / 2 * TILE
            tavern = next((b for b in s["buildings"] if b["kind"] in ("tavern",)), None)
            social = (tavern["work"] * TILE) if tavern else center
            robber = s["type"] == "robber"
            for b in s["buildings"]:
                kind = b["kind"]
                hx = (b["x0"] + b["x1"]) / 2 * TILE
                bed = b["beds"][0] if b["beds"] else None
                wx = b["work"] * TILE + 8

                def add(job, rank=1, female=False, fighter=False, noble=False, clergy=False, gear=None, title="",
                        work=None, home=None, bedx=None, patrol=None, field_=None, seat=None):
                    look = make_look(rng, rank, job, female, colors, clergy=clergy, soldier=fighter and not noble)
                    if robber:
                        look.pop("tabard", None)
                        look["tunic"] = (50, 44, 40)
                    nm = person_name(rng, female, job, noble=noble, place=seat or s["name"].split()[-1])
                    return self._new_person(name=nm, job=job, rank=rank, kingdom=k if not robber else "bandit",
                                            settlement=si, home_x=home or hx, work_x=work or wx, g=g, look=look,
                                            female=female, bed_x=bedx, field=field_, patrol=patrol,
                                            social_x=social, fighter=fighter, noble=noble, clergy=clergy,
                                            gear=gear or ("fists", "", "kleidung", ""), title=title, seat=seat)

                if robber:
                    if kind in ("keep", "hall"):
                        add("raubritter", 4, fighter=True, noble=True,
                            gear=("langschwert", "", "plattenrock", "topfhelm"), title="Raubritter",
                            work=wx, seat="Schwarzfels")
                    elif kind in ("tower", "smithy", "wall"):
                        add("bandit", 0, fighter=True, gear=(rng.choice(["axt", "knueppel", "speer", "schwert"]),
                                                              rng.choice(["holzschild", ""]), "gambeson", ""),
                            patrol=(s["x0"] * TILE + 40, s["x1"] * TILE - 40))
                    continue
                if kind == "house":
                    if s["type"] in ("village", "hamlet", "mine"):
                        job = "miner" if s["type"] == "mine" else "farmer"
                        f = fields[rng.randrange(len(fields))] if fields else None
                        fr = (f["x0"], f["x1"]) if f else None
                        gear = ("sichel", "", "kleidung", "") if job == "farmer" else ("spitzhacke", "", "kleidung", "")
                        add(job, 0 if k != "luebenau" else 1, bedx=bed, field_=fr, gear=gear,
                            work=(f["work"] * TILE if f else wx))
                        add(rng.choice(["farmer", "shepherd", "weaver"]), 0, female=True, bedx=bed,
                            work=(f["work"] * TILE if f else hx), field_=fr)
                        if rng.random() < 0.5:
                            add("child", 0, female=rng.random() < 0.5, bedx=bed)
                    else:
                        job = rng.choice(["merchant", "weaver", "baker", "potter", "carter", "shepherd"])
                        add(job, 2, bedx=bed)
                        add(rng.choice(["weaver", "baker", "merchant"]), 2, female=True, bedx=bed)
                        if rng.random() < 0.4:
                            add("child", 1, female=rng.random() < 0.5, bedx=bed)
                elif kind == "smithy":
                    add("smith", 2 if s["type"] not in ("village", "hamlet") else 1, bedx=bed,
                        gear=("hammer", "", "kleidung", ""))
                elif kind == "tavern":
                    add("innkeeper", 2, bedx=bed)
                elif kind == "church":
                    add("priest", 2, clergy=True, work=b["work"] * TILE + 8)
                elif kind == "cloister":
                    for _ in range(3):
                        add("monk", 1, clergy=True, bedx=bed, work=hx)
                elif kind == "mill":
                    add("miller", 1)
                elif kind in ("stall", "kontor"):
                    add("merchant", 2)
                elif kind == "dock":
                    add("fisher", 1, work=b["work"] * TILE)
                elif kind == "townhall":
                    add("mayor", 2, title="Bürgermeister", gear=("dolch", "", "kleidung", ""))
                elif kind == "hall":
                    if s["type"] == "capital" or (s["type"] == "castle" and kd["realm"] != "Königreich" and
                                                  kd["key"] not in self.rulers and kd["ruler_rank"] <= 7):
                        rr = kd["ruler_rank"]
                        rp = add("ruler", rr, fighter=True, noble=True, gear=("langschwert", "", "plattenrock", ""),
                                 title=kd["ruler"].split()[0], work=wx, seat=s["name"].replace("Burg ", ""))
                        rp.name = kd["ruler"]
                        rp.look["hat"] = "crown" if rr >= 8 else "coronet"
                        if k == "heiligenstein":
                            rp.look = make_look(rng, 8, "bishop", clergy=True)
                            rp.job = "ruler"
                        if k == "frostholm":
                            rp.female = True
                            rp.look["robe"] = True
                            rp.look["beard"] = False
                        self.rulers[k] = rp.id
                        self.lords[si] = rp.id
                    else:
                        lord_rank = {"castle": 6, "capital": 6}.get(s["type"], 5)
                        lp = add("lord", lord_rank, fighter=True, noble=True,
                                 gear=("schwert", "dreieckschild", "kettenhemd", ""), title="Graf" if lord_rank == 6
                                 else "Freiherr", work=wx, seat=s["name"].replace("Burg ", ""))
                        self.lords[si] = lp.id
                    add("knight", 4, fighter=True, noble=True, gear=("schwert", "dreieckschild", "kettenhemd",
                                                                    "topfhelm"),
                        title="Ritter", work=wx - 60, seat=s["name"].replace("Burg ", ""))
                elif kind in ("tower", "keep", "barracks"):
                    for _ in range(2 if kind != "barracks" else 4):
                        add("guard", 1, fighter=True, gear=(rng.choice(["speer", "schwert", "hellebarde"]),
                                                            rng.choice(["holzschild", ""]), "gambeson", "eisenhut"),
                            patrol=(s["x0"] * TILE + 60, s["x1"] * TILE - 60))
                elif kind == "wall" and s["type"] in ("town", "city", "capital"):
                    add("guard", 1, fighter=True, gear=("speer", "holzschild", "gambeson", "kettenhaube"),
                        work=b["x0"] * TILE + (40 if b["x0"] < (s["x0"] + s["x1"]) / 2 else -40),
                        patrol=(b["x0"] * TILE - 80, b["x0"] * TILE + 80))
            # village extras
            if s["type"] in ("village", "hamlet"):
                for _ in range(1 if s["type"] == "hamlet" else 2):
                    pass
                self._new_person(name=person_name(rng, False, "woodcutter"), job="woodcutter", rank=0, kingdom=k,
                                 settlement=si, home_x=center, work_x=s["x1"] * TILE + 200, g=g,
                                 look=make_look(rng, 0, "woodcutter"), gear=("axt", "", "kleidung", ""),
                                 social_x=social)
            if s["type"] in ("town", "city", "capital"):
                self._new_person(name=person_name(rng, False, "beggar"), job="beggar", rank=0, kingdom=k,
                                 settlement=si, home_x=center, work_x=center + rng.uniform(-100, 100), g=g,
                                 look=make_look(rng, 0), social_x=social)
        # ensure every kingdom has a ruler (falls back to its biggest settlement's lord)
        for kd in KINGDOMS:
            if kd["key"] not in self.rulers:
                cands = [si for si, s in enumerate(self.world.settlements) if s["kingdom"] == kd["key"]
                         and si in self.lords]
                if cands:
                    p = self.people[self.lords[cands[0]]]
                    p.name = kd["ruler"]
                    p.rank = kd["ruler_rank"]
                    p.job = "ruler"
                    self.rulers[kd["key"]] = p.id
                else:
                    # free city: the mayor rules
                    m = next((p for p in self.people if p.kingdom == kd["key"] and p.job == "mayor"), None)
                    if m:
                        m.name = kd["ruler"]
                        m.job = "ruler"
                        m.rank = kd["ruler_rank"]
                        self.rulers[kd["key"]] = m.id
            if kd["key"] not in self.rulers:
                # e.g. the prince-bishop: he holds court in his biggest church
                sis = [si for si, s in enumerate(self.world.settlements) if s["kingdom"] == kd["key"]]
                if not sis:
                    continue
                order = {"capital": 0, "city": 1, "town": 2, "castle": 3, "monastery": 4}
                si = min(sis, key=lambda i: order.get(self.world.settlements[i]["type"], 9))
                s = self.world.settlements[si]
                ch = next((b for b in s["buildings"] if b["kind"] in ("church", "hall", "townhall")), None)
                x = (ch["work"] * TILE + 40) if ch else (s["x0"] + s["x1"]) / 2 * TILE
                clergy = kd["realm"] == "Fürstbistum"
                look = make_look(self.rng, kd["ruler_rank"], "bishop" if clergy else "ruler", clergy=clergy,
                                 kingdom_colors=kd["colors"])
                rp = self._new_person(name=kd["ruler"], job="ruler", rank=kd["ruler_rank"], kingdom=kd["key"],
                                      settlement=si, home_x=x, work_x=x, g=s["g"], look=look, fighter=not clergy,
                                      noble=True, clergy=clergy, gear=("fists", "", "kleidung", ""),
                                      title=kd["ruler"].split()[0], seat=s["name"])
                self.rulers[kd["key"]] = rp.id
                self.lords[si] = rp.id

    # ------------------------------------------------------------------ politics
    def at_war(self, a, b=None):
        if b is None:
            return any(a in w for w in self.wars)
        return frozenset((a, b)) in self.wars

    def enemies_of(self, k):
        return [next(iter(w - {k})) for w in self.wars if k in w]

    def declare_war(self, a, b):
        self.wars.add(frozenset((a, b)))
        self.news.append((f"[Krieg|war]! {BY_KEY[a]['de']} declares war on {BY_KEY[b]['de']}.", ""))

    def make_peace(self, a, b):
        self.wars.discard(frozenset((a, b)))
        self.news.append((f"[Frieden|peace] between {BY_KEY[a]['de']} and {BY_KEY[b]['de']}.", ""))

    def settlements_of(self, k):
        return [si for si, o in self.owner.items() if o == k]

    def daily(self, day, world):
        rng = self.rng
        for si, m in self.markets.items():
            pop = len(self.by_settlement.get(si, []))
            m.daily(pop, rng)
        # trade caravans equalise prices a little
        keys = list(BASE_TARGET.keys())
        for _ in range(12 if len(self.markets) >= 2 else 0):
            a, b = rng.sample(list(self.markets.keys()), 2)
            k = rng.choice(keys)
            ma, mb = self.markets[a], self.markets[b]
            if ma.price(k) < mb.price(k) * 0.7 and ma.stock.get(k, 0) > 5:
                n = max(1, ma.stock[k] // 6)
                ma.stock[k] -= n
                mb.stock[k] = mb.stock.get(k, 0) + n
        # diplomacy
        keys = [k["key"] for k in KINGDOMS]
        if rng.random() < 0.18:
            a = rng.choice(keys)
            i = keys.index(a)
            nb = [keys[j] for j in (i - 1, i + 1) if 0 <= j < len(keys)]
            b = rng.choice(nb)
            if not self.at_war(a, b) and len(self.wars) < 3:
                self.declare_war(a, b)
        if self.wars and rng.random() < 0.10:
            w = rng.choice(list(self.wars))
            a, b = list(w)
            self.make_peace(a, b)
        # armies march
        for w in list(self.wars):
            a, b = list(w)
            for att, dfn in ((a, b), (b, a)):
                if rng.random() < 0.25 and sum(1 for ar in self.armies if ar.kingdom == att) < 2:
                    self.raise_army(att, dfn)

    def raise_army(self, att, dfn):
        rng = self.rng
        mine = self.settlements_of(att)
        theirs = self.settlements_of(dfn)
        if not mine or not theirs:
            return None
        src = rng.choice(mine)
        s0 = self.world.settlements[src]
        # target: the enemy settlement closest to the source
        tgt = min(theirs, key=lambda si: abs(self.world.settlements[si]["x0"] - s0["x0"]))
        units = [["speer", rng.randint(12, 30)], ["bogen", rng.randint(8, 20)]]
        if rng.random() < 0.6:
            units.append(["schild", rng.randint(10, 24)])
        if rng.random() < 0.5:
            units.append(["spiess", rng.randint(10, 24)])
        if rng.random() < 0.5:
            units.append(["ritter", rng.randint(4, 10)])
        self.army_ids += 1
        x = (s0["x0"] + s0["x1"]) / 2 * TILE
        ar = Army(self.army_ids, att, x, tgt, units)
        self.armies.append(ar)
        self.news.append((f"An [Heer|army] of {BY_KEY[att]['de']} marches on "
                          f"{self.world.settlements[tgt]['name']}.", ""))
        return ar

    def update_armies(self, dt, game):
        for ar in list(self.armies):
            tgt = self.world.settlements[ar.target]
            tx = (tgt["x0"] + tgt["x1"]) / 2 * TILE
            if ar.materialized:
                alive = [h for h in ar.haufen if not h.dead]
                if not alive:
                    self.armies.remove(ar)
                    self.news.append((f"The [Heer|army] of {BY_KEY[ar.kingdom]['de']} was destroyed.", ""))
                    continue
                ar.x = sum(h.x for h in alive) / len(alive)
                ar.units = [[h.unit.key, h.count] for h in alive]
                if abs(game.player.cx - ar.x) > 260 * TILE:
                    game.dematerialize_army(ar)
                continue
            if self.owner.get(ar.target) == ar.kingdom or not self.at_war(ar.kingdom, self.owner.get(ar.target)):
                self.armies.remove(ar)
                continue
            d = tx - ar.x
            if abs(d) > 40:
                ar.x += (1 if d > 0 else -1) * ar.speed * dt
            else:
                # abstract siege
                defence = 25 + len(self.by_settlement.get(ar.target, [])) * 1.5
                if ar.strength() > defence * self.rng.uniform(0.6, 1.4):
                    old = self.owner[ar.target]
                    self.owner[ar.target] = ar.kingdom
                    self.news.append((f"{tgt['name']} has fallen to {BY_KEY[ar.kingdom]['de']}! "
                                      f"([gefallen|fallen])", ""))
                    for pid in self.by_settlement.get(ar.target, []):
                        p = self.people[pid]
                        if p.kingdom == old:
                            p.kingdom = ar.kingdom
                            if "tabard" in p.look:
                                p.look["tabard"] = BY_KEY[ar.kingdom]["colors"]
                else:
                    self.news.append((f"The siege of {tgt['name']} failed.", ""))
                self.armies.remove(ar)
                continue
            if abs(game.player.cx - ar.x) < 150 * TILE:
                game.materialize_army(ar)
