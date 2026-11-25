"""World generation: heightmap -> strata -> caves/ores -> seas/lava -> edges -> flora -> settlements.

Generation is a generator function yielding (progress, label) so the loading screen can animate.
"""
import random

import numpy as np

from ..settings import SEA_LEVEL, WORLD_H, BEDROCK_ROWS
from ..society.kingdoms import KINGDOMS, BIOMES
from . import tiles as T
from . import structures as S
from .noise import fbm1, fbm2, smooth_array
from .world import World

BIOME_SHAPE = {
    #            base  amp   top           sub          deep
    "abyss": (130, 0, T.DEADGRASS.id, T.DIRT.id, T.STONE.id),
    "edge": (100, 8, T.DEADGRASS.id, T.DIRT.id, T.STONE.id),
    "plains": (102, 5, T.GRASS.id, T.DIRT.id, T.STONE.id),
    "forest": (100, 9, T.GRASS.id, T.DIRT.id, T.STONE.id),
    "moor": (109, 2, T.MUD.id, T.MUD.id, T.STONE.id),
    "hills": (94, 13, T.GRASS.id, T.DIRT.id, T.STONE.id),
    "mountains": (66, 34, T.GRASS.id, T.DIRT.id, T.STONE.id),
    "vineyard": (96, 11, T.GRASS.id, T.CLAY.id, T.STONE.id),
    "coast": (106, 4, T.GRASS.id, T.SAND.id, T.STONE.id),
    "ocean": (170, 14, T.SAND.id, T.SAND.id, T.STONE.id),
    "islet": (106, 4, T.SAND.id, T.SAND.id, T.STONE.id),
    "snow": (92, 16, T.SNOW.id, T.DIRT.id, T.STONE.id),
    "ashland": (101, 8, T.ASH.id, T.SANDSTONE.id, T.BASALT.id),
    "volcanic": (88, 22, T.ASH.id, T.BASALT.id, T.BASALT.id),
    "lavasea": (150, 6, T.BASALT.id, T.BASALT.id, T.BASALT.id),
}


def biome_columns(width):
    names = np.empty(width, dtype=object)
    regions = []
    for f0, f1, name in BIOMES:
        x0, x1 = int(f0 * width), int(f1 * width)
        names[x0:x1] = name
        regions.append((x0, x1, name))
    names[names == None] = "lavasea"  # noqa: E711
    return names, regions


def generate(width=48000, seed=1300, out=None):
    """Yields progress tuples; the finished World is stored in out['world']."""
    rng = random.Random(seed)
    w = World(width, WORLD_H, seed)
    H = WORLD_H
    xs = np.arange(width, dtype=np.float32)
    names, w.regions = biome_columns(width)
    w.abyss_w = int(BIOMES[0][1] * width)
    w.lava_w = width - int(0.99 * width)
    for k in KINGDOMS:
        w.kingdom_spans.append((int(k["span"][0] * width), int(k["span"][1] * width), k["key"]))
    yield 0.03, "Die Erde wird geformt… (shaping the earth)"

    # ---------------------------------------------------------------- heightmap
    base = np.array([BIOME_SHAPE[n][0] for n in names], dtype=np.float32)
    amp = np.array([BIOME_SHAPE[n][1] for n in names], dtype=np.float32)
    base = smooth_array(base, 241)
    amp = smooth_array(amp, 161)
    n1 = fbm1(xs, 1 / 180.0, seed, octaves=5)
    ridge = 1.0 - np.abs(fbm1(xs, 1 / 300.0, seed + 7, octaves=4) * 2 - 1)
    mtn = (names == "mountains") | (names == "volcanic")
    mtn_f = smooth_array(mtn.astype(np.float32), 301)
    height = base + amp * (n1 - 0.5) * 2.0 - mtn_f * ridge * 30
    # volcano cones
    for vx in np.linspace(0.955, 0.985, 3) * width:
        d = np.abs(xs - vx)
        height -= np.clip(1 - d / 220.0, 0, 1) ** 1.6 * 40
    # ocean shelf: make sure the sea floor really is below sea level, coasts slope
    height = np.clip(height, 24, H - 30)
    surface = height.astype(np.int32)

    # lakes & a river valley (carved as dips that will fill with water)
    lakes = []
    for _ in range(int(width / 3500)):
        cx = rng.randint(int(0.04 * width), int(0.6 * width))
        if names[cx] in ("plains", "forest", "moor", "hills", "vineyard"):
            r = rng.randint(14, 40)
            depth = rng.randint(4, 9)
            x0, x1 = max(0, cx - r), min(width, cx + r)
            rim = int(surface[x0:x1].min())
            t = np.linspace(-1, 1, x1 - x0)
            surface[x0:x1] = np.maximum(surface[x0:x1], (rim + 1 + depth * np.cos(t * np.pi / 2)).astype(np.int32))
            lakes.append((x0, x1, rim + 1))
    yield 0.10, "Siedlungen werden geplant… (planning settlements)"

    # ---------------------------------------------------------------- settlements (flatten heightmap first)
    plans = []
    for k in KINGDOMS:
        k0, k1 = int(k["span"][0] * width), int(k["span"][1] * width)
        specs = k["settlements"]
        n = len(specs)
        for i, (stype, sname) in enumerate(specs):
            swidth = {"village": 110, "hamlet": 60, "castle": 90, "town": 150, "city": 230, "capital": 300,
                      "monastery": 90, "port": 70, "mine": 70, "robber": 80}[stype]
            if stype == "port":
                # ports sit on the shore facing open water
                plans.append(dict(type=stype, name=sname, kingdom=k["key"], width=swidth, x0=None))
                continue
            slot = (k1 - k0) / n
            cx = int(k0 + slot * (i + 0.5) + rng.uniform(-slot * 0.2, slot * 0.2))
            if k["key"] == "randmark" and sname == "Erlenbach":
                cx = int(k0 + (k1 - k0) * 0.22)
            cx = max(k0 + swidth, min(k1 - swidth, cx))
            # never in water: slide toward land
            tries = 0
            while surface[cx] >= SEA_LEVEL - 1 and tries < 400:
                cx += -7 if k["key"] in ("frostholm", "glutmark") else -11
                tries += 1
            plans.append(dict(type=stype, name=sname, kingdom=k["key"], width=swidth, x0=cx - swidth // 2))
    # ports: find shoreline
    for p in plans:
        if p["type"] != "port":
            continue
        k = next(kk for kk in KINGDOMS if kk["key"] == p["kingdom"])
        k0, k1 = int(k["span"][0] * width), int(k["span"][1] * width)
        if p["kingdom"] == "luebenau":
            xs_ = range(k1 - 5, k0, -1)
            side = 1
        elif p["kingdom"] == "frostholm":
            xs_ = range(k0 + 5, k1)
            side = -1
        else:
            xs_ = range(k0 + 5, k1)
            side = -1
        shore = None
        for x in xs_:
            if surface[x] < SEA_LEVEL - 1:
                shore = x
                break
        if shore is None:
            shore = k0 + 20
        p["shore"] = shore
        p["side"] = side
        p["x0"] = shore - p["width"] + 2 if side == 1 else shore - 2
    for p in plans:
        x0 = max(5, p["x0"])
        x1 = min(width - 6, x0 + p["width"])
        seg = surface[x0:x1]
        g = int(np.median(seg))
        g = min(g, SEA_LEVEL - 3)
        if p["type"] == "capital":
            g = min(g, int(seg.min()) + 2)
        surface[x0:x1] = g
        ramp = 24
        for i in range(1, ramp + 1):
            t = i / (ramp + 1)
            for xx, side in ((x0 - i, 1), (x1 - 1 + i, -1)):
                if 0 <= xx < width:
                    surface[xx] = int(round(g * (1 - t) + surface[xx] * t))
        p["x0"], p["x1"], p["g"] = x0, x1, g
    w.surface[:] = surface
    yield 0.18, "Felsen und Erde werden geschichtet… (layering rock)"

    # ---------------------------------------------------------------- strata, caves, ores (in strips)
    top_ids = np.array([BIOME_SHAPE[n][2] for n in names], dtype=np.uint8)
    sub_ids = np.array([BIOME_SHAPE[n][3] for n in names], dtype=np.uint8)
    deep_ids = np.array([BIOME_SHAPE[n][4] for n in names], dtype=np.uint8)
    dirt_depth = (4 + fbm1(xs, 1 / 60.0, seed + 3, octaves=2) * 6).astype(np.int32)
    no_caves = np.zeros(width, dtype=bool)
    for p in plans:
        no_caves[max(0, p["x0"] - 10):p["x1"] + 10] = True
    no_caves |= surface >= SEA_LEVEL - 4  # never undermine seas
    seabed = surface >= SEA_LEVEL
    no_caves |= np.convolve(seabed.astype(np.float32), np.ones(61), mode="same") > 0
    ys = np.arange(H, dtype=np.float32)[None, :]
    strip = 2048
    kingdom_col = np.empty(width, dtype=object)
    for x0, x1, key in w.kingdom_spans:
        kingdom_col[x0:x1] = key
    for s0 in range(0, width, strip):
        s1 = min(width, s0 + strip)
        sx = xs[s0:s1, None]
        surf = surface[s0:s1, None]
        depth = ys - surf
        solid = depth >= 0
        fg = np.zeros((s1 - s0, H), dtype=np.uint8)
        fg[solid] = np.broadcast_to(deep_ids[s0:s1, None], fg.shape)[solid]
        subm = solid & (depth < dirt_depth[s0:s1, None])
        fg[subm] = np.broadcast_to(sub_ids[s0:s1, None], fg.shape)[subm]
        topm = depth == 0
        fg[topm] = np.broadcast_to(top_ids[s0:s1, None], fg.shape)[topm]
        # sea floors: sand + gravel patches + clay
        gn = noise_patch = fbm2(sx, ys, 1 / 23.0, 1 / 9.0, seed + 11, octaves=2)
        under_sea = (surf >= SEA_LEVEL) & solid & (depth < 6)
        fg[under_sea & (gn > 0.62)] = T.GRAVEL.id
        fg[under_sea & (gn < 0.3)] = T.CLAY.id
        # caves: winding tunnels + deep caverns
        cn = fbm2(sx, ys, 1 / 64.0, 1 / 26.0, seed + 21, octaves=3)
        cn2 = fbm2(sx, ys, 1 / 40.0, 1 / 40.0, seed + 31, octaves=2)
        tunnel = np.abs(cn - 0.5) < (0.022 + np.clip(depth, 0, 120) / 120.0 * 0.03)
        cavern = (cn2 > 0.70) & (depth > 30)
        cave = (tunnel | cavern) & (depth > 7) & (ys < H - BEDROCK_ROWS - 2)
        cave &= ~no_caves[s0:s1, None]
        # ores
        on = fbm2(sx, ys, 1 / 6.0, 1 / 6.0, seed + 41, octaves=2)
        stone_like = (fg == T.STONE.id) | (fg == T.BASALT.id) | (fg == T.SANDSTONE.id)
        kc = kingdom_col[s0:s1]
        silver_mult = np.array([1.0 if k == "hochburg" else 0.0 for k in kc], dtype=np.float32)[:, None]
        salt_mult = np.array([1.0 if k in ("luebenau", "heiligenstein") else 0.0 for k in kc],
                             dtype=np.float32)[:, None]
        glut_mult = np.array([1.0 if k == "glutmark" else 0.0 for k in kc], dtype=np.float32)[:, None]
        fg[stone_like & (on > 0.80) & (depth > 6)] = T.COAL.id
        fg[stone_like & (on < 0.17) & (depth > 14)] = T.IRON.id
        r = fbm2(sx, ys, 1 / 5.0, 1 / 5.0, seed + 51, octaves=1)
        fg[stone_like & (r > 1.0 - 0.08 * silver_mult) & (depth > 18)] = T.SILVER.id
        fg[stone_like & (r < 0.04 * salt_mult + 0.0) & (depth > 10)] = T.SALT.id
        fg[stone_like & (r > 0.965) & (depth > 70)] = T.GOLD_ORE.id
        fg[stone_like & (on > 1.0 - 0.12 * glut_mult) & (depth > 20)] = T.GLUTSTEIN.id
        fg[stone_like & (on < 0.08) & (depth > 30) & (r > 0.5)] = T.GRAVEL.id
        fg[cave] = 0
        bg = np.zeros_like(fg)
        bgm = depth >= 3
        bg[bgm] = T.BG_DIRT
        bg[bgm & (depth > 18)] = T.BG_STONE
        glutcol = np.array([k == "glutmark" for k in kc])[:, None]
        bg[bgm & glutcol] = T.BG_ASH
        # deep lava pools
        lava = cave & (ys > H - 34)
        fg[:, H - BEDROCK_ROWS:] = T.BEDROCK.id
        w.fg[s0:s1] = fg
        w.bg[s0:s1] = bg
        w.liq[s0:s1][lava] = 8
        w.lava[s0:s1][lava] = True
        yield 0.18 + 0.42 * s1 / width, "Höhlen und Erze… (caves & ores)"

    # ---------------------------------------------------------------- seas, lakes, lava sea
    yield 0.62, "Das Graue Meer füllt sich… (filling the sea)"
    for x in range(width):
        g = surface[x]
        if g > SEA_LEVEL and names[x] in ("ocean", "coast", "islet", "snow", "ashland", "lavasea", "plains",
                                          "volcanic"):
            w.liq[x, SEA_LEVEL:g] = 8
            if names[x] == "lavasea":
                w.lava[x, SEA_LEVEL:g] = True
    for x0, x1, lvl in lakes:
        for x in range(x0, x1):
            g = surface[x]
            if g > lvl:
                w.liq[x, lvl:g] = 8
    # lava sea: everything east of the last volcano drowns in fire
    ls = int(0.99 * width)
    for x in range(ls - 60, width):
        g = max(surface[x], SEA_LEVEL + 6)
        w.fg[x, :g] = 0
        w.liq[x, SEA_LEVEL + 2:g] = 8
        w.lava[x, SEA_LEVEL + 2:g] = True
        w.fg[x, g] = T.BASALT.id

    # ---------------------------------------------------------------- world edges: the land is a floating slab
    yield 0.66, "Der Rand der Welt… (the edge of the world)"
    aw = w.abyss_w
    w.fg[:aw] = 0
    w.bg[:aw] = 0
    w.liq[:aw] = 0
    w.lava[:aw] = False
    crust = 140
    for i in range(crust):
        x = aw + i
        bottom = int(surface[x] + 6 + (i / crust) ** 0.7 * (H - surface[x]) + rng.randint(-2, 2))
        if bottom < H:
            w.fg[x, bottom:] = 0
            w.bg[x, bottom:] = 0
            w.liq[x, bottom:] = 0
    # jagged lip
    for i, x in enumerate(range(aw, aw + 6)):
        top = surface[x] + (6 - i) + rng.randint(0, 1)   # the brink slopes down into the void
        w.fg[x, :top] = 0
    # east end: the lava pours over the brink
    le = width - 40
    for i in range(40):
        x = le + i
        bottom = int(H - (i / 40) * (H - SEA_LEVEL - 10))
        w.fg[x, bottom:] = 0
        w.liq[x, bottom:] = 0
        w.lava[x, bottom:] = False
    w.fg[width - 6:] = 0
    w.liq[width - 6:] = 0
    # floating stones over and near the abyss
    for _ in range(60):
        fx = rng.randint(30, aw + 1200)
        fy = rng.randint(30, 95)
        rw, rh = rng.randint(3, 9), rng.randint(2, 4)
        for x in range(fx - rw, fx + rw):
            depth = rh - int(abs(x - fx) / rw * rh)
            for y in range(fy, fy + max(1, depth)):
                if 0 <= x < width:
                    w.fg[x, y] = T.FLOATROCK.id
            if 0 <= x < width and depth > 0:
                w.fg[x, fy - 1] = T.DEADGRASS.id if rng.random() < 0.7 else T.FLOATROCK.id

    # ---------------------------------------------------------------- settlements
    yield 0.70, "Dörfer, Städte und Burgen werden errichtet… (raising villages, towns, castles)"
    for p in plans:
        recs = build_settlement(w, p, rng)
        p["buildings"] = recs
        w.settlements.append(dict(name=p["name"], type=p["type"], kingdom=p["kingdom"], x0=p["x0"],
                                  x1=p["x1"], g=p["g"], buildings=recs))
    w.settlements.sort(key=lambda s: s["x0"])

    # ---------------------------------------------------------------- flora & decoration
    yield 0.85, "Bäume wachsen… (growing trees)"
    occupied = np.zeros(width, dtype=bool)
    for s in w.settlements:
        occupied[max(0, s["x0"] - 4):s["x1"] + 4] = True
    tree_density = {"edge": 0.015, "plains": 0.05, "forest": 0.22, "moor": 0.05, "hills": 0.07,
                    "mountains": 0.06, "vineyard": 0.03, "coast": 0.02, "snow": 0.12, "ashland": 0.012,
                    "volcanic": 0.008, "islet": 0.03}
    x = aw + 10
    while x < width - 60:
        b = names[x]
        g = int(w.surface[x])
        if occupied[x] or b not in tree_density or g >= SEA_LEVEL or w.fg[x, g] == 0:
            x += 1
            continue
        top = w.fg[x, g]
        if not T.NATURAL[top] or w.fg[x, g - 1] != 0 or w.liq[x, g - 1]:
            x += 1
            continue
        r = rng.random()
        if r < tree_density[b]:
            kind = {"snow": "pine", "mountains": "pine" if rng.random() < 0.7 else "oak",
                    "edge": "dead", "ashland": "dead", "volcanic": "dead"}.get(b, "oak")
            if b == "forest" and rng.random() < 0.3:
                kind = "pine"
            if b == "moor" and rng.random() < 0.5:
                kind = "dead"
            grow_tree(w, x, g, kind, rng)
            x += rng.randint(4, 8)
            continue
        if b in ("plains", "forest", "hills", "vineyard", "mountains", "coast", "moor") and top in (
                T.GRASS.id, T.MUD.id):
            q = rng.random()
            if q < 0.22:
                w.fg[x, g - 1] = T.TALLGRASS.id
            elif q < 0.27:
                w.fg[x, g - 1] = T.FLOWER.id
            elif q < 0.29:
                w.fg[x, g - 1] = T.BUSH.id
            elif b == "vineyard" and q < 0.5 and g < 100:
                w.fg[x, g - 1] = T.VINE.id
        x += 1
    # seabed life + shipwrecks
    for x in range(aw, width - 60):
        g = int(w.surface[x])
        if g > SEA_LEVEL + 2 and w.liq[x, g - 1] and not w.lava[x, g - 1] and w.fg[x, g - 1] == 0:
            r = rng.random()
            if r < 0.14:
                hgt = rng.randint(1, 5)
                for y in range(g - hgt, g):
                    if w.liq[x, y]:
                        w.fg[x, y] = T.SEAWEED.id
            elif r < 0.16:
                w.fg[x, g - 1] = T.SHELL.id
    ocean_cols = [x for x0, x1, b in w.regions if b == "ocean" for x in (x0 + (x1 - x0) // 3,
                                                                        x0 + 2 * (x1 - x0) // 3)]
    for x in ocean_cols:
        S.shipwreck(w, x, int(w.surface[x]), rng)
    # cave mushrooms
    for _ in range(width // 6):
        x = rng.randint(aw + 50, width - 80)
        y = rng.randint(SEA_LEVEL, H - 10)
        if w.fg[x, y] == 0 and T.SOLID[w.fg[x, y + 1]] and w.bg[x, y] and not w.liq[x, y]:
            w.fg[x, y] = T.MUSHROOM.id

    # ---------------------------------------------------------------- signposts between settlements
    yield 0.95, "Wegweiser werden aufgestellt… (placing signposts)"
    for a, b in zip(w.settlements, w.settlements[1:]):
        sx = (a["x1"] + b["x0"]) // 2
        g = w.ground_at(sx)
        if g < SEA_LEVEL and w.fg[sx, g - 1] == 0 and not w.liq[sx, g - 1]:
            w.fg[sx, g - 1] = T.SIGN.id
            dw = (sx - a["x1"]) * 16 / 1000 * 0.4
            de = (b["x0"] - sx) * 16 / 1000 * 0.4
            w.signs[(sx, g - 1)] = (f"← {a['name']}  {max(0.1, dw):.1f} Meilen (miles)\n"
                                    f"→ {b['name']}  {max(0.1, de):.1f} Meilen (miles)")
    yield 1.0, "Fertig! (done)"
    if out is not None:
        out["world"] = w


def grow_tree(w, x, g, kind, rng):
    if kind == "oak":
        h = rng.randint(4, 7)
        for y in range(g - h, g):
            w.fg[x, y] = T.LOG.id
        r = rng.randint(3, 5)
        cy = g - h - r // 2
        rx, ry = r + 0.6, r * 0.85
        for dx in range(-r - 1, r + 2):
            for dy in range(-r, r + 1):
                d = (dx / rx) ** 2 + (dy / ry) ** 2
                if d <= 1.0 + rng.uniform(-0.15, 0.1):
                    xx, yy = x + dx, cy + dy
                    if 0 <= xx < w.w and 0 <= yy < w.h and w.fg[xx, yy] == 0:
                        w.fg[xx, yy] = T.LEAVES.id
        # a trunk that reaches into the crown
        for y in range(cy, g - h):
            if 0 <= y < w.h:
                w.fg[x, y] = T.LOG.id
    elif kind == "pine":
        h = rng.randint(9, 15)
        for y in range(g - h, g):
            w.fg[x, y] = T.LOG.id
        for i in range(h - 2):
            y = g - h + i
            half = min(4, 1 + i // 3)
            for dx in range(-half, half + 1):
                xx = x + dx
                if 0 <= xx < w.w and w.fg[xx, y] == 0:
                    w.fg[xx, y] = T.PINE.id
        w.fg[x, g - h - 1] = T.PINE.id
    else:  # dead
        h = rng.randint(4, 8)
        for y in range(g - h, g):
            w.fg[x, y] = T.LOG.id
        for k, d in enumerate((-1, 1)):
            by = g - h + 1 + rng.randint(0, max(1, h // 2))
            length = rng.randint(2, 3)
            for i in range(1, length + 1):
                xx = x + d * i
                if 0 <= xx < w.w and w.fg[xx, by] == 0:
                    w.fg[xx, by] = T.LOG.id
            tip = x + d * (length + 1)
            if 0 <= tip < w.w and w.fg[tip, by - 1] == 0:
                w.fg[tip, by - 1] = T.LOG.id      # the limb turns upward at its end


def build_settlement(w, p, rng):
    t, x0, x1, g = p["type"], p["x0"], p["x1"], p["g"]
    k = p["kingdom"]
    style = {"frostholm": "snow", "glutmark": "ash"}.get(k, "peasant")
    recs = []
    # clear the air above the footprint and pave
    S.clear_box(w, x0, x1, g - 40, g - 1)
    for x in range(x0, x1):
        if not T.SOLID[w.fg[x, g]]:
            w.fg[x, g] = T.DIRT.id
        if w.fg[x, g] in (T.DIRT.id,):
            w.fg[x, g] = BIOME_TOP.get(k, T.GRASS.id)
    if t in ("village", "hamlet"):
        cur = x0 + 6
        n_houses = 4 if t == "hamlet" else rng.randint(6, 8)
        if k in ("waldheim", "randmark"):
            S.palisade(w, x0 + 1, g)
            S.palisade(w, x1 - 2, g)
        for i in range(n_houses):
            if cur + 12 > x1 - 6:
                break
            if i == 2 and t == "village":
                recs.append(S.church(w, cur, g, width=11, rng=rng))
                cur += 15
                continue
            if i == 3:
                recs.append(S.well(w, cur + 1, g))
                cur += 4
            if i == 4 and t == "village":
                recs.append(S.windmill(w, cur, g))
                cur += 8
                continue
            hw = rng.randint(7, 10)
            kind = "smithy" if i == 1 and t == "village" else "house"
            h = S.house(w, cur, g, width=hw, height=4, style=style, door_side=rng.choice((-1, 1)), rng=rng,
                        kind=kind)
            if kind == "smithy":
                S._put(w, h["x0"] + 2, g - 1, T.ANVIL.id)
                S._put(w, h["x0"] + 3, g - 1, T.FORGE.id)
            recs.append(h)
            cur += hw + rng.randint(2, 4)
            if rng.random() < 0.55 and cur + 14 < x1 - 6 and style != "ash":
                fw = rng.randint(8, 14)
                recs.append(S.field(w, cur, cur + fw, g, rng))
                cur += fw + 2
        if t == "village" and k not in ("glutmark",):
            fw = min(16, x1 - 6 - cur)
            if fw > 5:
                recs.append(S.field(w, cur, cur + fw, g, rng))
    elif t in ("town", "city", "capital"):
        gate_w = S.wall_tower(w, x0 + 2, g, height=8, thick=2, gate=True)
        recs.append(gate_w)
        cur = x0 + 6
        end = x1 - 6
        castle_end = None
        if t == "capital":
            crecs, castle_end = S.castle(w, cur, g, rng, size="capital")
            recs.extend(crecs)
            cur = castle_end + 4
        n = 0
        while cur + 12 < end:
            n += 1
            if n == 3:
                recs.append(S.church(w, cur, g, width=15, rng=rng))
                cur += 18
                continue
            if n == 5:
                # market square
                for i in range(3):
                    recs.append(S.stall(w, cur + i * 5, g, rng))
                recs.append(S.well(w, cur + 16, g))
                cur += 20
                continue
            hw = rng.randint(8, 11)
            kind = {2: "tavern", 4: "smithy", 6: "townhall"}.get(n, "house")
            if kind == "townhall" and t == "town":
                kind = "house"
            h = S.house(w, cur, g, width=hw + (3 if kind in ("tavern", "townhall") else 0), height=4,
                        style="burgher" if style == "peasant" else style, door_side=rng.choice((-1, 1)), rng=rng,
                        kind=kind)
            if kind == "smithy":
                S._put(w, h["x0"] + 2, g - 1, T.ANVIL.id)
                S._put(w, h["x0"] + 3, g - 1, T.FORGE.id)
            if kind == "tavern":
                S._put(w, h["x0"] + 3, g - 1, T.BARREL.id)
                S._put(w, h["x0"] + 4, g - 1, T.BARREL.id)
            recs.append(h)
            cur = h["x1"] + rng.randint(1, 3)
        recs.append(S.wall_tower(w, x1 - 4, g, height=8, thick=2, gate=True))
    elif t in ("castle", "robber"):
        crecs, _ = S.castle(w, x0 + 4, g, rng, size="castle")
        recs.extend(crecs)
    elif t == "monastery":
        recs.append(S.wall_tower(w, x0 + 2, g, height=6, thick=1, gate=True, battlement=False))
        recs.append(S.church(w, x0 + 8, g, width=19, rng=rng))
        h = S.house(w, x0 + 32, g, width=14, height=4, style="stone", rng=rng, kind="cloister")
        recs.append(h)
        recs.append(S.well(w, x0 + 50, g))
        recs.append(S.field(w, x0 + 54, x0 + 70, g, rng))
        recs.append(S.wall_tower(w, x1 - 4, g, height=6, thick=1, gate=True, battlement=False))
    elif t == "mine":
        recs.append(S.house(w, x0 + 6, g, width=9, height=4, style=style, rng=rng, kind="house"))
        recs.append(S.house(w, x0 + 18, g, width=8, height=4, style=style, rng=rng, kind="smithy"))
        S._put(w, x0 + 20, g - 1, T.ANVIL.id)
        S._put(w, x0 + 21, g - 1, T.FORGE.id)
        S.mine_shaft(w, x0 + 32, g, 60, rng)
        recs.append(dict(kind="mine", x0=x0 + 32, x1=x0 + 34, g=g, door=x0 + 33, beds=[], work=x0 + 33,
                         style="mine", top=g - 3))
        recs.append(S.house(w, x0 + 40, g, width=9, height=4, style=style, rng=rng, kind="house"))
    elif t == "port":
        shore, side = p["shore"], p["side"]
        if side == 1:
            recs.append(S.house(w, x0 + 4, g, width=12, height=5, style="burgher" if style == "peasant" else style,
                                rng=rng, kind="kontor"))
            recs.append(S.house(w, x0 + 20, g, width=8, height=4, style=style, rng=rng, kind="house"))
            recs.append(S.house(w, x0 + 31, g, width=9, height=4, style=style, rng=rng, kind="tavern"))
        else:
            recs.append(S.house(w, x1 - 16, g, width=12, height=5, style=style, rng=rng, kind="kontor"))
            recs.append(S.house(w, x1 - 27, g, width=8, height=4, style=style, rng=rng, kind="house"))
            recs.append(S.house(w, x1 - 38, g, width=9, height=4, style=style, rng=rng, kind="tavern"))
        sx = shore + side * 1
        while 0 < sx < w.w - 1 and not w.liq[sx, SEA_LEVEL + 1]:
            sx += side
        recs.append(S.dock(w, sx - side * 4, SEA_LEVEL, 26, side, rng))
    # torches on the street
    for r in recs:
        if r["kind"] in ("house", "tavern", "townhall", "kontor") and rng.random() < 0.5:
            tx = r["x1"] + 1
            if 0 <= tx < w.w and w.fg[tx, g - 2] == 0:
                w.fg[tx, g - 2] = T.TORCH.id
    return recs


BIOME_TOP = {"glutmark": T.ASH.id, "frostholm": T.SNOW.id, "randmark": T.GRASS.id}
