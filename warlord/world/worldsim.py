"""Interactive environment: liquids, fire, growth, collapse.

* Liquids flow cell-by-cell around the player (water pours off the world's edge into the abyss).
* Fire spreads through thatch, Fachwerk, planks and forest — faster downwind, slower in rain.
* Crops ripen (not in winter, faster in rain), grass spreads, saplings become trees, leaves decay.
* Built structures need support: dig out a wall's foundation (sapping) and it collapses.
"""
import random

from ..settings import TILE, SEA_LEVEL
from . import tiles as T


class FallingBlock:
    kind = "falling"

    def __init__(self, tx, ty, tid):
        self.x = tx * TILE
        self.y = ty * TILE
        self.vy = 0.0
        self.tid = tid
        self.removed = False
        self.uid = id(self)

    def update(self, game, dt):
        w = game.world
        self.vy = min(700.0, self.vy + 1300 * dt)
        self.y += self.vy * dt
        tx = int((self.x + 8) // TILE)
        ty = int((self.y + TILE) // TILE)
        if self.y > w.pixel_h() + 100:
            self.removed = True
            return
        if w.inside(tx, ty) and (T.SOLID[w.fg[tx, ty]] or T.PLATFORM_T[w.fg[tx, ty]]):
            land = ty - 1
            self.removed = True
            for h in game.humanoids + game.animals:
                if not h.dead and h.x < self.x + TILE and h.x + h.w > self.x and h.y < self.y + TILE < h.feet + 8:
                    h.take_hit(game, None, 18 + self.vy * 0.03, "blunt", 30, ("unblockable",), source_x=h.cx)
            if T.TILES[self.tid].falls and w.inside(tx, land) and w.fg[tx, land] == 0:
                w.set(tx, land, self.tid)
            else:
                drop = T.TILES[self.tid].drop
                if drop and game.rng.random() < 0.5:
                    game.drop_item(drop, 1, self.x + 8, self.y)
                game.fx.debris(self.x + 8, self.y + 8, T.TILES[self.tid].color, 5)

    def draw(self, surf, ox, oy):
        from ..gfx import tileart
        surf.blit(tileart.tile_surface(self.tid, 0, 0), (self.x - ox, self.y - oy))


class WorldSim:
    def __init__(self, game):
        self.game = game
        self.fire_tick = 0.0
        self.rand_tick = 0.0
        self.rng = random.Random(7)

    # ------------------------------------------------------------------ liquids
    def liquids(self, cx_tile, budget=2500):
        w = self.game.world
        act = w.active_liquid
        if not act:
            return
        lo, hi = cx_tile - 160, cx_tile + 160
        cells = [c for c in act if lo <= c[0] <= hi]
        if len(cells) > budget:
            cells = self.rng.sample(cells, budget)
        cells.sort(key=lambda c: -c[1])  # bottom first
        liq, lava, fg = w.liq, w.lava, w.fg
        W, H = w.w, w.h
        for (x, y) in cells:
            a = int(liq[x, y])
            act.discard((x, y))
            if a == 0:
                continue
            is_lava = bool(lava[x, y])
            changed = False
            # off the edge of the world
            if y >= H - 1 or x <= w.abyss_w or x >= W - 6:
                if x <= w.abyss_w or x >= W - 6:
                    liq[x, y] = 0
                    w.mark_liquid(x, y)
                    continue
            # down
            if y + 1 < H and not T.SOLID[fg[x, y + 1]]:
                b = int(liq[x, y + 1])
                if b > 0 and bool(lava[x, y + 1]) != is_lava:
                    self._mix(x, y + 1)
                    liq[x, y] = 0
                    changed = True
                elif b < 8:
                    m = min(a, 8 - b)
                    liq[x, y + 1] = b + m
                    lava[x, y + 1] = is_lava
                    a -= m
                    liq[x, y] = a
                    changed = True
            # sideways
            if a > 0:
                for dx in (self.rng.choice((-1, 1)),):
                    for d in (dx, -dx):
                        nx = x + d
                        if 0 <= nx < W and not T.SOLID[fg[nx, y]]:
                            n = int(liq[nx, y])
                            if n and bool(lava[nx, y]) != is_lava:
                                self._mix(nx, y)
                                changed = True
                                continue
                            if n + 1 < a:
                                m = (a - n) // 2 if a - n > 1 else 0
                                if m <= 0:
                                    continue
                                liq[nx, y] = n + m
                                lava[nx, y] = is_lava
                                a -= m
                                liq[x, y] = a
                                changed = True
                            elif x <= w.abyss_w + 2 and nx < x:
                                liq[x, y] = 0
                                changed = True
            if liq[x, y] == 0:
                lava[x, y] = False
            if changed:
                w.mark_liquid(x, y)
                for nx, ny in ((x, y), (x + 1, y), (x - 1, y), (x, y - 1), (x, y + 1)):
                    if 0 <= nx < W and 0 <= ny < H and liq[nx, ny]:
                        act.add((nx, ny))
                        w.mark_liquid(nx, ny)

    def _mix(self, x, y):
        w = self.game.world
        w.liq[x, y] = 0
        w.lava[x, y] = False
        w.set(x, y, T.OBSIDIAN.id, wake=False)
        self.game.fx.smoke(x * TILE + 8, y * TILE, 4)
        self.game.sfx("hiss")

    # ------------------------------------------------------------------ fire
    def fire(self, dt):
        g = self.game
        w = g.world
        self.fire_tick += dt
        if self.fire_tick < 0.25:
            return
        step = self.fire_tick
        self.fire_tick = 0.0
        rain = g.env.rain()
        wind = g.env.wind
        new = []
        for (x, y), t in list(w.fires.items()):
            t += step
            tid = int(w.fg[x, y])
            if not T.FLAMMABLE[tid] or w.liq[x, y] > 2:
                del w.fires[(x, y)]
                continue
            if self.rng.random() < rain * 0.06 * step * 4:
                del w.fires[(x, y)]
                continue
            w.fires[(x, y)] = t
            for dx, dy in ((1, 0), (-1, 0), (0, -1), (0, 1), (1, -1), (-1, -1)):
                nx, ny = x + dx, y + dy
                if not w.inside(nx, ny) or (nx, ny) in w.fires:
                    continue
                if T.FLAMMABLE[w.fg[nx, ny]]:
                    p = 0.06 * step * 4 * (1.0 + (wind * dx) * 1.5) * (1.0 - rain * 0.8)
                    if dy < 0:
                        p *= 1.6  # flames climb
                    if self.rng.random() < p:
                        new.append((nx, ny))
            burn = 4.0 if tid in (T.LEAVES.id, T.PINE.id, T.THATCH.id, T.HAY.id, T.TALLGRASS.id) else 9.0
            if t > burn:
                del w.fires[(x, y)]
                g.break_tile(x, y, drop=False, by=None)
        for c in new:
            w.fires[c] = 0.0

    # ------------------------------------------------------------------ growth & decay
    def random_ticks(self, dt, cx_tile):
        g = self.game
        w = g.world
        env = g.env
        self.rand_tick += dt
        n = int(self.rand_tick * 900)
        if n <= 0:
            return
        self.rand_tick = 0.0
        season = env.season()
        grow = 0.0 if season == 3 else (1.0 + env.rain() * 1.5) * (1.3 if season == 1 else 1.0)
        rng = self.rng
        for _ in range(n):
            x = cx_tile + rng.randint(-120, 120)
            if not (0 <= x < w.w):
                continue
            y = int(w.surface[x]) + rng.randint(-14, 4)
            if not (1 <= y < w.h - 1):
                continue
            t = int(w.fg[x, y])
            if t in T.CROP_STAGES and t != T.WHEAT4.id:
                if rng.random() < 0.08 * grow:
                    w.set(x, y, t + 1, wake=False)
            elif t == T.SAPLING.id:
                if rng.random() < 0.02 * grow:
                    w.fg[x, y] = 0
                    from .generator import grow_tree
                    grow_tree(w, x, y + 1, "oak" if w.biome_at(x) not in ("snow", "mountains") else "pine", rng)
                    for cx in range(x - 5, x + 6):
                        for cy in range(y - 16, y + 2):
                            if w.inside(cx, cy):
                                w.mark(cx, cy)
            elif t in (T.LEAVES.id, T.PINE.id):
                found = False
                for dx in range(-4, 5):
                    for dy in range(-1, 6):
                        if w.inside(x + dx, y + dy) and w.fg[x + dx, y + dy] == T.LOG.id:
                            found = True
                            break
                    if found:
                        break
                if not found:
                    w.set(x, y, 0, wake=False)
                    if rng.random() < 0.08:
                        g.drop_item("sapling", 1, x * TILE + 8, y * TILE + 8)
            elif t == T.DIRT.id and w.fg[x, y - 1] == 0 and not w.liq[x, y - 1]:
                for dx in (-1, 1):
                    if w.inside(x + dx, y) and w.fg[x + dx, y] == T.GRASS.id and rng.random() < 0.2 * grow:
                        w.set(x, y, T.GRASS.id, wake=False)
                        break
            elif t == T.GRASS.id and w.fg[x, y - 1] == 0 and rng.random() < 0.002 * grow:
                w.set(x, y - 1, T.TALLGRASS.id if rng.random() < 0.8 else T.FLOWER.id, wake=False)

    # ------------------------------------------------------------------ support / collapse
    def check_support(self, x, y):
        """Called after a tile at (x,y) disappears. Unsupported built structures collapse."""
        g = self.game
        w = g.world
        # sand and gravel above fall
        ay = y - 1
        while w.inside(x, ay) and T.FALLS[w.fg[x, ay]]:
            tid = int(w.fg[x, ay])
            w.set(x, ay, 0)
            g.spawn_falling(x, ay, tid)
            ay -= 1
        for sx, sy in ((x, y - 1), (x - 1, y), (x + 1, y), (x, y + 1)):
            if not w.inside(sx, sy):
                continue
            if not (T.BUILT[w.fg[sx, sy]] and T.SOLID[w.fg[sx, sy]]):
                continue
            comp = self._component(sx, sy, 500)
            if comp is None:
                continue
            g.fx.text(sx * TILE, sy * TILE - 20, "Einsturz!", (255, 200, 150), gloss="collapse!")
            g.camera.shake = max(g.camera.shake, 6)
            g.sfx("collapse")
            for i, (cx, cy) in enumerate(sorted(comp, key=lambda c: -c[1])):
                tid = int(w.fg[cx, cy])
                w.set(cx, cy, 0)
                w.fires.pop((cx, cy), None)
                if i < 160:
                    g.spawn_falling(cx, cy, tid)
            break

    def _component(self, sx, sy, limit):
        """BFS over built tiles; returns the set if NOT supported, else None."""
        w = self.game.world
        seen = {(sx, sy)}
        stack = [(sx, sy)]
        while stack:
            x, y = stack.pop()
            for nx, ny in ((x, y + 1), (x - 1, y), (x + 1, y), (x, y - 1)):
                if (nx, ny) in seen or not w.inside(nx, ny):
                    continue
                t = int(w.fg[nx, ny])
                if not T.SOLID[t] and not T.PLATFORM_T[t] and not T.CLIMB[t]:
                    continue
                if not T.BUILT[t] and t not in (T.LADDER.id, T.LOG.id):
                    if T.SOLID[t]:
                        return None   # rests on natural ground
                    continue
                seen.add((nx, ny))
                stack.append((nx, ny))
                if len(seen) > limit:
                    return None       # big structure: assume it holds
        return seen
