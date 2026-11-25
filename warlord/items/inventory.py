"""The bag: a sack you fill with things, limited by weight, plus a small belt for what you grab quickly.

Not a grid of slots. Things go into the bag as they are (twelve split logs are twelve logs) and the bag view
lays them out on a cloth. What is too bulky for any bag (a trunk, a door, a ladder) is carried in your arms
and slows you down. The belt holds four things within reach: weapon, tool, bow, torch...

The class keeps the old Inventory interface (count, has, add, remove, take, held, money, selected, slots)
so trade, crafting, quests and the story keep working.
"""
from .items import ITEMS, weight, BULKY

EQUIP_CATS = ("weapon", "tool", "shield", "armor", "helmet")


class Inventory:
    BELT = 4
    CAPACITY = 36.0     # kg a leather Rucksack carries

    def __init__(self):
        self.items = {}            # key -> count
        self.quality = {}          # key -> average quality of shaped pieces (0..1)
        self.belt = [None] * self.BELT
        self.selected = 0
        self.money = 0
        self.capacity = self.CAPACITY
        self.layout = {}           # key -> (x, y, angle) where it lies on the cloth in the bag view
        self.new = set()           # recently added (the bag view highlights them)

    # ------------------------------------------------------------------ the old API
    def count(self, key):
        return self.items.get(key, 0)

    def has(self, req):
        return all(self.count(k) >= n for k, n in req.items())

    def weight(self):
        return sum(weight(k) * n for k, n in self.items.items())

    def free(self):
        return self.capacity - self.weight()

    def add(self, key, n=1, quality=None, force=False):
        """Returns how many did not fit."""
        if key == "silver_coin":
            self.money += n
            return 0
        d = ITEMS.get(key)
        if d is None or n <= 0:
            return n
        wt = weight(key)
        fit = n
        if not force and wt > 0:
            fit = max(0, min(n, int(self.free() // wt + 1e-6)))
        if fit <= 0:
            return n
        old = self.items.get(key, 0)
        if quality is not None:
            q0 = self.quality.get(key, quality)
            self.quality[key] = (q0 * old + quality * fit) / (old + fit)
        self.items[key] = old + fit
        self.new.add(key)
        if d.cat in EQUIP_CATS or key in ("torch",) or d.cat == "heal":
            if key not in self.belt and None in self.belt and d.cat not in ("armor", "helmet", "shield"):
                self.belt[self.belt.index(None)] = key
        return n - fit

    def remove(self, key, n=1):
        have = self.items.get(key, 0)
        if have < n:
            return False
        if have == n:
            del self.items[key]
            self.quality.pop(key, None)
            if key in self.belt:
                self.belt[self.belt.index(key)] = None
        else:
            self.items[key] = have - n
        return True

    def take(self, req):
        if not self.has(req):
            return False
        for k, n in req.items():
            self.remove(k, n)
        return True

    def held(self):
        k = self.belt[self.selected] if 0 <= self.selected < self.BELT else None
        if k is not None and self.items.get(k, 0) <= 0:
            self.belt[self.selected] = None
            return None
        return k

    def held_def(self):
        k = self.held()
        return ITEMS.get(k) if k else None

    @property
    def slots(self):
        """Compatibility: a list of [key, count] (belt first)."""
        out = [[k, self.items[k]] if k and self.items.get(k) else None for k in self.belt]
        out += [[k, n] for k, n in self.items.items() if k not in self.belt]
        return out

    def swap(self, a, b):
        if 0 <= a < self.BELT and 0 <= b < self.BELT:
            self.belt[a], self.belt[b] = self.belt[b], self.belt[a]

    def to_belt(self, key, slot=None):
        if key not in self.items:
            return False
        if key in self.belt:
            i = self.belt.index(key)
            self.belt[i] = None
        if slot is None:
            slot = self.belt.index(None) if None in self.belt else self.selected
        self.belt[slot] = key
        return True

    @staticmethod
    def bulky(key):
        return key in BULKY

    def keys_sorted(self):
        order = {"weapon": 0, "tool": 1, "shield": 2, "armor": 3, "helmet": 4, "ammo": 5, "food": 6, "heal": 7,
                 "material": 8, "place": 9, "misc": 10, "mount": 11}
        return sorted(self.items, key=lambda k: (order.get(ITEMS[k].cat, 12), ITEMS[k].de))

    # ------------------------------------------------------------------ old saves
    def __setstate__(self, d):
        if "slots" in d and "items" not in d:
            items = {}
            for s in d["slots"]:
                if s:
                    items[s[0]] = items.get(s[0], 0) + s[1]
            d = dict(items=items, quality={}, belt=[None] * self.BELT, selected=0, money=d.get("money", 0),
                     capacity=self.CAPACITY, layout={}, new=set())
        self.__dict__.update(d)
