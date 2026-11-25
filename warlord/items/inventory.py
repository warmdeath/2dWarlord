"""Inventory with a 10-slot hotbar and equipment slots."""
from .items import ITEMS


class Inventory:
    SIZE = 40
    HOTBAR = 10

    def __init__(self):
        self.slots = [None] * self.SIZE   # [key, count]
        self.selected = 0
        self.money = 0                     # Pfennig

    def count(self, key):
        return sum(s[1] for s in self.slots if s and s[0] == key)

    def has(self, req):
        return all(self.count(k) >= n for k, n in req.items())

    def add(self, key, n=1):
        if key == "silver_coin":
            self.money += n
            return 0
        d = ITEMS.get(key)
        if d is None:
            return n
        for s in self.slots:
            if n <= 0:
                break
            if s and s[0] == key and s[1] < d.stack:
                take = min(n, d.stack - s[1])
                s[1] += take
                n -= take
        for i, s in enumerate(self.slots):
            if n <= 0:
                break
            if s is None:
                take = min(n, d.stack)
                self.slots[i] = [key, take]
                n -= take
        return n  # leftover

    def remove(self, key, n=1):
        for i in range(len(self.slots) - 1, -1, -1):
            s = self.slots[i]
            if n <= 0:
                break
            if s and s[0] == key:
                take = min(n, s[1])
                s[1] -= take
                n -= take
                if s[1] <= 0:
                    self.slots[i] = None
        return n == 0

    def take(self, req):
        if not self.has(req):
            return False
        for k, n in req.items():
            self.remove(k, n)
        return True

    def held(self):
        s = self.slots[self.selected]
        return s[0] if s else None

    def held_def(self):
        k = self.held()
        return ITEMS.get(k) if k else None

    def swap(self, a, b):
        self.slots[a], self.slots[b] = self.slots[b], self.slots[a]
