"""Generates the polygon world: the same geography as before (7 realms, 15 biomes, seas, lakes, the Abyss in
the west and the Fire Sea in the east), now as smooth terrain lines, carved cave passages, water bodies,
faceted trees and buildings made of real pieces.

A generator function yielding (progress, label) so the loading screen can animate; the finished world is
stored in out['world'].
"""
import math
import random

import numpy as np
from shapely.geometry import LineString, Point
from shapely.ops import unary_union
from shapely import affinity

from ..settings import SEA_LEVEL, WORLD_H, TILE
from ..society.kingdoms import KINGDOMS, BIOMES
from ..world.noise import fbm1, smooth_array
from .world import PolyWorld, Water
from . import prefab as S
from .flora import Tree
from .prefab import Decor

BIOME_SHAPE = {"abyss": (130, 0), "edge": (100, 8), "plains": (102, 5), "forest": (100, 9), "moor": (109, 2),
               "hills": (94, 13), "mountains": (66, 34), "vineyard": (96, 11), "coast": (106, 4),
               "ocean": (170, 14), "islet": (106, 4), "snow": (92, 16), "ashland": (101, 8),
               "volcanic": (88, 22), "lavasea": (150, 6)}
SEA_BIOMES = ("ocean", "coast", "islet", "snow", "ashland", "lavasea", "plains", "volcanic")
CULTURE_CROPS = {"randmark": ("rye", "rye", "oat"), "waldheim": ("rye", "oat"), "hochburg": ("wheat", "oat"),
                 "heiligenstein": ("wheat", "flax"), "luebenau": ("flax", "wheat", "rye"),
                 "frostholm": ("oat", "turnip"), "glutmark": ("turnip",)}
SWIDTH = {"village": 110, "hamlet": 60, "castle": 90, "town": 150, "city": 230, "capital": 300, "monastery": 90,
          "port": 70, "mine": 70, "robber": 80}


def biome_columns(width):
    names = np.empty(width, dtype=object)
    regions = []
    for f0, f1, name in BIOMES:
        x0, x1 = int(f0 * width), int(f1 * width)
        names[x0:x1] = name
        regions.append((x0, x1, name))
    names[names == None] = "lavasea"  # noqa: E711
    return names, regions


def limit_slope(h, max_step, fixed):
    """Relax a height profile so no column-to-column step exceeds max_step (keeps hills walkable)."""
    for _ in range(3):
        for i in range(1, len(h)):
            if not fixed[i] and h[i] - h[i - 1] > max_step:
                h[i] = h[i - 1] + max_step
        for i in range(len(h) - 2, -1, -1):
            if not fixed[i] and h[i] - h[i + 1] > max_step:
                h[i] = h[i + 1] + max_step
        for i in range(1, len(h)):
            if not fixed[i] and h[i - 1] - h[i] > max_step:
                h[i] = h[i - 1] - max_step
        for i in range(len(h) - 2, -1, -1):
            if not fixed[i] and h[i + 1] - h[i] > max_step:
                h[i] = h[i + 1] - max_step
    return h


def generate(width=48000, seed=1300, out=None):
    rng = random.Random(seed)
    w = PolyWorld(width, WORLD_H, seed)
    H = WORLD_H
    xs = np.arange(width, dtype=np.float32)
    names, w.regions = biome_columns(width)
    w.abyss_w = int(BIOMES[0][1] * width)
    w.lava_w = width - int(0.99 * width)
    for k in KINGDOMS:
        w.kingdom_spans.append((int(k["span"][0] * width), int(k["span"][1] * width), k["key"]))
    yield 0.03, "Die Erde wird geformt… (shaping the earth)"

    base = smooth_array(np.array([BIOME_SHAPE[n][0] for n in names], dtype=np.float32), 241)
    amp = smooth_array(np.array([BIOME_SHAPE[n][1] for n in names], dtype=np.float32), 161)
    n1 = fbm1(xs, 1 / 180.0, seed, octaves=5)
    ridge = 1.0 - np.abs(fbm1(xs, 1 / 300.0, seed + 7, octaves=4) * 2 - 1)
    mtn = (names == "mountains") | (names == "volcanic")
    mtn_f = smooth_array(mtn.astype(np.float32), 301)
    height = base + amp * (n1 - 0.5) * 2.0 - mtn_f * ridge * 30
    for vx in np.linspace(0.955, 0.985, 3) * width:
        d = np.abs(xs - vx)
        height -= np.clip(1 - d / 220.0, 0, 1) ** 1.6 * 40
    height = np.clip(height, 24, H - 30)
    # vineyards are cut into terraces with stone retaining walls; hills keep small plateaus
    terr = names == "vineyard"
    quant = np.floor(height / 2.0) * 2.0
    height = np.where(terr, quant + np.clip((height - quant) * 2 - 1.2, 0, 2) * 0.5, height)
    height = height.astype(np.float64)

    lakes = []
    for _ in range(int(width / 3500)):
        cx = rng.randint(int(0.04 * width), int(0.6 * width))
        if names[cx] in ("plains", "forest", "moor", "hills", "vineyard"):
            r = rng.randint(14, 40)
            depth = rng.randint(4, 9)
            x0, x1 = max(0, cx - r), min(width, cx + r)
            rim = float(height[x0:x1].min())
            t = np.linspace(-1, 1, x1 - x0)
            height[x0:x1] = np.maximum(height[x0:x1], rim + 1 + depth * np.cos(t * np.pi / 2))
            lakes.append((x0, x1, int(rim) + 1))
    yield 0.10, "Siedlungen werden geplant… (planning settlements)"

    plans = []
    for k in KINGDOMS:
        k0, k1 = int(k["span"][0] * width), int(k["span"][1] * width)
        specs = k["settlements"]
        n = len(specs)
        for i, (stype, sname) in enumerate(specs):
            swidth = SWIDTH[stype]
            if stype == "port":
                plans.append(dict(type=stype, name=sname, kingdom=k["key"], width=swidth, x0=None))
                continue
            slot = (k1 - k0) / n
            cx = int(k0 + slot * (i + 0.5) + rng.uniform(-slot * 0.2, slot * 0.2))
            if k["key"] == "randmark" and sname == "Erlenbach":
                cx = int(k0 + (k1 - k0) * 0.22)
            cx = max(k0 + swidth, min(k1 - swidth, cx))
            tries = 0
            while height[cx] >= SEA_LEVEL - 1 and tries < 400:
                cx += -7 if k["key"] in ("frostholm", "glutmark") else -11
                tries += 1
            plans.append(dict(type=stype, name=sname, kingdom=k["key"], width=swidth, x0=cx - swidth // 2))
    for p in plans:
        if p["type"] != "port":
            continue
        k = next(kk for kk in KINGDOMS if kk["key"] == p["kingdom"])
        k0, k1 = int(k["span"][0] * width), int(k["span"][1] * width)
        if p["kingdom"] == "luebenau":
            xs_, side = range(k1 - 5, k0, -1), 1
        else:
            xs_, side = range(k0 + 5, k1), -1
        shore = next((x for x in xs_ if height[x] < SEA_LEVEL - 1), k0 + 20)
        p["shore"], p["side"] = shore, side
        p["x0"] = shore - p["width"] + 2 if side == 1 else shore - 2
    fixed = np.zeros(width, dtype=bool)
    for p in plans:
        x0 = max(5, p["x0"])
        x1 = min(width - 6, x0 + p["width"])
        seg = height[x0:x1]
        g = int(np.median(seg))
        g = min(g, SEA_LEVEL - 3)
        if p["type"] == "capital":
            g = min(g, int(seg.min()) + 2)
        height[x0:x1] = g
        fixed[x0:x1] = True
        ramp = 30
        for i in range(1, ramp + 1):
            t = (i / (ramp + 1)) ** 1.3
            for xx in (x0 - i, x1 - 1 + i):
                if 0 <= xx < width:
                    height[xx] = g * (1 - t) + height[xx] * t
        p["x0"], p["x1"], p["g"] = x0, x1, g
    # no slope steeper than 45° away from the world's edges and the sea floor
    edge_fixed = fixed.copy()
    edge_fixed[:w.abyss_w + 8] = True
    edge_fixed[int(0.99 * width) - 62:] = True
    height = limit_slope(height, 0.95, edge_fixed)
    w.top[:width] = (height * TILE).astype(np.float32)
    w.top[width] = w.top[width - 1]
    w.surface[:] = np.round(height).astype(np.int32)
    yield 0.20, "Felsen werden geschichtet… (layering rock)"

    # ---------------------------------------------------------------- the crust and its broken edges
    aw = w.abyss_w
    w.bottom[:] = (H - 2) * TILE
    w.bottom[:aw] = w.top[:aw]                 # nothing: the void
    crust = 140
    for i in range(crust):
        x = aw + i
        w.bottom[x] = (height[x] + 6 + (i / crust) ** 0.7 * (H - height[x]) + rng.uniform(-1.5, 1.5)) * TILE
    for i in range(6):
        w.top[aw + i] += (6 - i) * TILE * 0.8
    le = width - 40
    for i in range(41):
        x = le + i
        if x <= width:
            w.bottom[x] = (H - (i / 40) * (H - SEA_LEVEL - 10)) * TILE
    w.bottom[width - 6:] = w.top[width - 6:]
    # floating stones over the Abyss
    for _ in range(60):
        fx = rng.randint(30, aw + 160) * TILE
        fy = rng.randint(30, 95) * TILE
        rw, rh = rng.randint(3, 9) * TILE, rng.randint(2, 4) * TILE
        pts = [(fx - rw, fy), (fx - rw * 0.5, fy - rng.uniform(4, 10)), (fx + rw * 0.4, fy - rng.uniform(4, 10)),
               (fx + rw, fy + rng.uniform(-2, 4)), (fx + rw * 0.3, fy + rh), (fx - rw * 0.2, fy + rh * 1.2),
               (fx - rw * 0.8, fy + rh * 0.4)]
        w.rocks.append(pts)
    yield 0.30, "Höhlen werden gegraben… (carving caves)"

    # ---------------------------------------------------------------- caves
    no_caves = np.zeros(width, dtype=bool)
    for p in plans:
        no_caves[max(0, p["x0"] - 10):p["x1"] + 10] = True
    seabed = height >= SEA_LEVEL - 4
    no_caves |= np.convolve(seabed.astype(np.float32), np.ones(61), mode="same") > 0
    no_caves[:aw + 160] = True
    no_caves[width - 120:] = True
    for lx0, lx1, _ in lakes:
        no_caves[max(0, lx0 - 20):lx1 + 20] = True
    x = aw + 200
    count = 0
    while x < width - 200:
        x += rng.randint(50, 150)
        if x >= width - 200 or no_caves[x]:
            continue
        entrance = names[x] in ("hills", "mountains", "forest", "snow", "volcanic") and rng.random() < 0.3
        sx = x * TILE
        if entrance:
            sy = w.top[x] - 6
            ang = rng.choice((0.55, math.pi - 0.55))
        else:
            sy = w.top[x] + rng.uniform(14, 70) * TILE
            ang = rng.choice((0.0, math.pi)) + rng.uniform(-0.4, 0.4)
        pts = [(sx, sy)]
        steps = rng.randint(14, 46)
        r = rng.uniform(15, 26)
        cy_ = sy
        cx_ = sx
        for i in range(steps):
            ang += rng.uniform(-0.35, 0.35)
            if entrance and i < 5:
                ang = max(0.35, min(math.pi - 0.35, ang))
            ln = rng.uniform(22, 40)
            cx_ += math.cos(ang) * ln
            cy_ += math.sin(ang) * ln * 0.7
            col = int(cx_ // TILE)
            if not (aw + 160 < col < width - 120) or no_caves[col]:
                break
            surf = w.top[col]
            if (not entrance or i > 5) and cy_ < surf + 9 * TILE:
                cy_ = surf + 9 * TILE
                ang = abs(ang) if math.cos(ang) > 0 else math.pi - abs(ang)
            cy_ = min(cy_, (H - 8) * TILE)
            pts.append((cx_, cy_))
        if len(pts) < 3:
            continue
        geom = LineString(pts).buffer(r, quad_segs=3)
        if rng.random() < 0.35:
            ex, ey = pts[len(pts) // 2]
            cav = affinity.scale(Point(ex, ey).buffer(rng.uniform(50, 110), quad_segs=4), 1.0, rng.uniform(0.5, 0.8))
            geom = unary_union([geom, cav])
        geom = geom.simplify(3.0)
        w.add_cave(geom)
        count += 1
        # ore in the walls: veins sit just inside the rock along the passage
        for (px, py) in pts[1::3]:
            if rng.random() < 0.6:
                depth = (py - w.top[int(px // TILE)]) / TILE
                kname = w.kingdom_at(int(px // TILE))
                pool = ["coal", "iron", "iron", "stone"]
                if depth > 18 and kname == "hochburg":
                    pool += ["silver", "silver"]
                if kname in ("luebenau", "heiligenstein"):
                    pool += ["salt"]
                if kname == "glutmark":
                    pool += ["glutstein", "glutstein"]
                if depth > 60:
                    pool += ["gold"]
                w.ores.append(dict(x=float(px + rng.uniform(-r, r)), y=float(py + r * 0.9), kind=rng.choice(pool), hp=40,
                                   left=rng.randint(3, 7)))
        for (px, py) in pts[2::4]:
            if rng.random() < 0.4:
                w.index_add("decor_chunks", px, Decor("mushroom", px, py + r * 0.85, 8, 8))
        if count % 40 == 0:
            yield 0.30 + 0.25 * x / width, "Höhlen werden gegraben… (carving caves)"

    # ---------------------------------------------------------------- water
    yield 0.58, "Das Graue Meer füllt sich… (filling the sea)"
    sea_px = SEA_LEVEL * TILE
    wet = np.array([height[i] > SEA_LEVEL and names[i] in SEA_BIOMES for i in range(width)])
    i = 0
    while i < width:
        if wet[i]:
            j = i
            while j < width and wet[j]:
                j += 1
            lava = names[min(width - 1, (i + j) // 2)] == "lavasea"
            w.water.append(Water(i * TILE - 4, j * TILE + 4, sea_px + (2 * TILE if lava else 0), lava))
            i = j
        else:
            i += 1
    for x0, x1, lvl in lakes:
        w.water.append(Water(x0 * TILE, x1 * TILE, lvl * TILE, False))
    # the Fire Sea at the eastern end
    ls = int(0.99 * width)
    for x in range(ls - 60, width + 1):
        w.top[x] = max(w.top[x], (SEA_LEVEL + 6) * TILE)
    w.water.append(Water((ls - 60) * TILE, width * TILE, (SEA_LEVEL + 2) * TILE, True))
    w.water.sort(key=lambda r: r.x0)

    # ---------------------------------------------------------------- settlements
    yield 0.66, "Dörfer, Städte und Burgen werden errichtet… (raising villages, towns, castles)"
    for n_, p in enumerate(plans):
        recs = build_settlement(w, p, rng)
        p["buildings"] = recs
        w.settlements.append(dict(name=p["name"], type=p["type"], kingdom=p["kingdom"], x0=p["x0"], x1=p["x1"],
                                  g=p["g"], buildings=recs))
        if n_ % 4 == 0:
            yield 0.66 + 0.18 * n_ / len(plans), "Dörfer, Städte und Burgen… (villages, towns, castles)"
    w.settlements.sort(key=lambda s: s["x0"])

    # ---------------------------------------------------------------- trees and plants
    yield 0.85, "Bäume wachsen… (growing trees)"
    occupied = np.zeros(width, dtype=bool)
    for s in w.settlements:
        occupied[max(0, s["x0"] - 4):s["x1"] + 4] = True
    tree_density = {"edge": 0.015, "plains": 0.05, "forest": 0.24, "moor": 0.05, "hills": 0.08,
                    "mountains": 0.07, "vineyard": 0.03, "coast": 0.02, "snow": 0.12, "ashland": 0.012,
                    "volcanic": 0.008, "islet": 0.03}
    x = aw + 10
    while x < width - 60:
        b = names[x]
        g = height[x]
        if occupied[x] or b not in tree_density or g >= SEA_LEVEL - 0.5 or w.water_level(x * TILE + 8) is not None:
            x += 1
            continue
        r = rng.random()
        if r < tree_density[b]:
            kind = {"snow": "fir" if rng.random() < 0.6 else "pine",
                    "mountains": "pine" if rng.random() < 0.7 else "fir", "edge": "dead", "ashland": "dead",
                    "volcanic": "dead"}.get(b, "oak")
            if b == "forest":
                q = rng.random()
                kind = "pine" if q < 0.25 else "beech" if q < 0.5 else "birch" if q < 0.62 else "lime" if q < 0.7 \
                    else "oak"
            elif b in ("plains", "hills") and rng.random() < 0.22:
                kind = rng.choice(("birch", "lime", "beech"))
            if b == "moor":
                kind = "dead" if rng.random() < 0.4 else "willow" if rng.random() < 0.6 else "birch"
            px = x * TILE + rng.uniform(0, TILE)
            hgt = {"pine": 230, "fir": 210, "birch": 170, "dead": 120, "willow": 140}.get(kind, 190)
            hgt *= rng.uniform(0.7, 1.3)
            trunk = {"birch": 8, "pine": 11, "fir": 12, "dead": 9}.get(kind, 14) * (hgt / 190) ** 0.7
            t = Tree(kind, px, w.surface_y(px) + 3, hgt, trunk, rng.randint(0, 1 << 30))
            w.trees.append(t)
            w.index_add("tree_chunks", px, t)
            x += rng.randint(3, 7)
            continue
        px = x * TILE + rng.uniform(0, TILE)
        gy = w.surface_y(px)
        q = rng.random()
        if b in ("plains", "forest", "hills", "vineyard", "mountains", "coast", "moor", "snow"):
            kind = None
            if q < 0.03:
                kind = "bush"
            elif q < 0.06 and b in ("plains", "hills", "vineyard"):
                kind = "flowers"
            elif b in ("forest", "moor") and q < 0.12:
                kind = "fern"
            elif b == "vineyard" and q < 0.4 and x % 3 == 0:
                kind = "vine"
            elif b == "hills" and q < 0.08:
                kind = "heather"
            elif q > 0.993 and b in ("plains", "hills", "mountains", "forest"):
                # Findling: a glacial boulder, a real rock you can climb
                rw = rng.uniform(16, 30)
                w.rocks.append([(px - rw, gy + 6), (px - rw * 0.8, gy - rw * 0.6), (px - rw * 0.1, gy - rw * 1.0),
                                (px + rw * 0.7, gy - rw * 0.7), (px + rw, gy + 6)])
            if kind:
                w.index_add("decor_chunks", px, Decor(kind, px, gy + 2, 14, 12, seed=rng.randint(0, 9999)))
        if x > 0 and w.water_level(px + 24) is not None and w.water_level(px) is None and rng.random() < 0.6:
            w.index_add("decor_chunks", px, Decor("reeds", px + 6, gy + 2, 14, 24, seed=rng.randint(0, 9999)))
        x += 1
    # seabed life + shipwrecks
    for wr in w.water:
        if wr.lava:
            continue
        xx = wr.x0 + 20
        while xx < wr.x1 - 20:
            gy = w.surface_y(xx)
            if gy > wr.level + 40:
                q = rng.random()
                if q < 0.25:
                    w.index_add("decor_chunks", xx, Decor("seaweed", xx, gy + 2, 8, rng.uniform(20, 70),
                                                          seed=rng.randint(0, 9999)))
                elif q < 0.28:
                    w.index_add("decor_chunks", xx, Decor("shell", xx, gy + 1, 6, 4))
            xx += rng.uniform(10, 40)
    for x0, x1, b in w.regions:
        if b == "ocean":
            for xx in (x0 + (x1 - x0) // 3, x0 + 2 * (x1 - x0) // 3):
                S.shipwreck(w, xx, int(w.surface[xx]), rng)

    # ---------------------------------------------------------------- bridges
    yield 0.93, "Brücken werden geschlagen… (building bridges)"
    for lx0, lx1, lvl in lakes:
        if not w.settlement_at(lx0, margin=5):
            S.bridge(w, lx0 - 1, lx1, lvl - 2, rng, stone=True)
    x = aw + 200
    while x < width - 200:
        if names[x] in ("mountains", "hills", "snow") and not occupied[x]:
            h0 = height[x]
            for span in range(6, 44):
                x2 = x + span
                if x2 >= width or occupied[x2]:
                    break
                h2 = height[x2]
                if abs(h2 - h0) <= 1 and span > 6:
                    deepest = float(height[x + 1:x2].max())
                    if deepest - h0 >= 8:
                        S.bridge(w, x, x2, int(min(h0, h2)) - 1, rng, stone=names[x] != "snow" and span < 24)
                        x = x2
                    break
                if h2 < h0 - 1:
                    break
        x += 3
    yield 0.96, "Wegweiser werden aufgestellt… (placing signposts)"
    for a, b in zip(w.settlements, w.settlements[1:]):
        sx = (a["x1"] + b["x0"]) // 2
        px = sx * TILE + 8
        if w.water_level(px) is None:
            dw = (sx - a["x1"]) * 16 / 1000 * 0.4
            de = (b["x0"] - sx) * 16 / 1000 * 0.4
            text = (f"← {a['name']}  {max(0.1, dw):.1f} Meilen (miles)\n"
                    f"→ {b['name']}  {max(0.1, de):.1f} Meilen (miles)")
            w.signs[(sx, int(w.surface[sx]) - 1)] = text
            w.index_add("decor_chunks", px, Decor("sign", px, w.surface_y(px) + 2, 20, 30, text=text))
    w.trees.sort(key=lambda t: t.x)
    for b in w.buildings:
        for (x, y) in b.smoke:
            w.smokers.append((x / TILE - 0.5, y / TILE))
    yield 1.0, "Fertig! (done)"
    if out is not None:
        out["world"] = w


def build_settlement(w, p, rng):
    t, x0, x1, g = p["type"], p["x0"], p["x1"], p["g"]
    k = p["kingdom"]
    style = {"frostholm": "longhouse", "glutmark": "basalt", "waldheim": "log", "randmark": "chained"}.get(k,
                                                                                                       "peasant")
    town_style = {"hochburg": "tower", "luebenau": "brick", "frostholm": "stone", "glutmark": "basalt"}.get(
        k, "burgher")
    crops = CULTURE_CROPS.get(k, ("wheat",))
    recs = []
    if t in ("village", "hamlet"):
        cur = x0 + 6
        n_houses = 4 if t == "hamlet" else rng.randint(6, 8)
        if k in ("waldheim", "randmark"):
            S.palisade(w, x0 + 1, g, rng=rng)
            S.palisade(w, x1 - 2, g, rng=rng)
        for i in range(n_houses):
            if cur + 12 > x1 - 6:
                break
            if i == 2 and t == "village":
                recs.append(S.church(w, cur, g, width=11, rng=rng))
                cur += 15
                continue
            if i == 3:
                recs.append(S.well(w, cur + 1, g, rng=rng))
                cur += 4
            if i == 4 and t == "village":
                recs.append(S.windmill(w, cur, g, rng=rng))
                cur += 9
                continue
            hw = rng.randint(7, 10) if style != "longhouse" else rng.randint(13, 16)
            if cur + hw + 6 > x1 - 6:
                break
            kind = "smithy" if i == 1 and t == "village" else "house"
            h = S.house(w, cur, g, width=hw, height=4, style=style, door_side=rng.choice((-1, 1)), rng=rng, kind=kind)
            if kind == "smithy":
                smithy_fittings(w, h)
            recs.append(h)
            cur += hw + rng.randint(2, 4) + (5 if style == "chained" else 0)
            if rng.random() < 0.55 and cur + 22 < x1 - 6 and style != "basalt":
                fw = rng.randint(8, 14)
                cur += 5
                recs.append(S.field(w, cur, cur + fw, g, rng, rng.choice(crops)))
                S.walkway(w, cur, cur + fw, g, rng)
                cur += fw + 8
        if t == "village" and k not in ("glutmark",):
            fw = min(16, x1 - 10 - cur)
            if fw > 5:
                recs.append(S.field(w, cur + 5, cur + 5 + fw, g, rng, rng.choice(crops)))
                S.walkway(w, cur + 5, cur + 5 + fw, g, rng)
        if k == "waldheim" and x1 + 12 < w.w:
            S.charcoal_kiln(w, x1 + 8, g, rng)
        workbench(w, x0 + 3, g)
    elif t in ("town", "city", "capital"):
        recs.append(S.wall_tower(w, x0 + 2, g, height=8, thick=2, gate=True, rng=rng))
        cur = x0 + 6
        end = x1 - 6
        if t == "capital":
            crecs, castle_end = S.castle(w, cur, g, rng, size="capital")
            recs.extend(crecs)
            cur = castle_end + 4
        n = 0
        prev_tower = None
        while cur + 12 < end:
            n += 1
            if n == 3:
                recs.append(S.church(w, cur, g, width=15, rng=rng))
                cur += 18
                prev_tower = None
                continue
            if n == 5:
                for i in range(3):
                    recs.append(S.stall(w, cur + i * 5, g, rng))
                recs.append(S.well(w, cur + 17, g, rng=rng))
                workbench(w, cur + 19, g)
                cur += 21
                prev_tower = None
                continue
            kind = {2: "tavern", 4: "smithy", 6: "townhall"}.get(n, "house")
            if kind == "townhall" and t == "town":
                kind = "house"
            st = town_style
            floors = None
            if st == "tower":
                hw = rng.randint(6, 8)
                floors = rng.randint(3, 5) if kind == "house" else 2
            elif st == "brick":
                hw = rng.randint(7, 9)
            else:
                hw = rng.randint(8, 11)
            hw += 3 if kind in ("tavern", "townhall") else 0
            if cur + hw + 2 > end:
                break
            h = S.house(w, cur, g, width=hw, height=4, style=st, door_side=rng.choice((-1, 1)), rng=rng, kind=kind,
                        floors=floors)
            if kind == "smithy":
                smithy_fittings(w, h)
            if kind == "tavern":
                b = S.building(w, h["bid"])
                for i in (3, 4):
                    d = Decor("barrel", (h["x0"] + i) * TILE, g * TILE, 14, 16, bld=b.id)
                    b.decor.append(d)
                    w.index_add("decor_chunks", d.x, d)
            recs.append(h)
            gap = rng.randint(1, 3) if st != "tower" else 3
            if st == "tower" and prev_tower is not None and h.get("floors") and prev_tower.get("floors"):
                # a plank bridge between the upper floors of neighbouring tower houses
                fy = min(h["floors"][0], prev_tower["floors"][0]) * TILE
                B = S.Builder(w, "skybridge", "wood", rng)
                B.rect((prev_tower["x1"] + 1) * TILE - 2, fy, h["x0"] * TILE + 2, fy + 6, "plank", "floor",
                       platform=True, detail="boards")
                B.back((prev_tower["x1"] + 1) * TILE, fy - 16, h["x0"] * TILE, fy - 14, "timber", "rail")
                B.finish(None)
            prev_tower = h if st == "tower" else None
            cur = h["x1"] + 1 + gap
        recs.append(S.wall_tower(w, x1 - 5, g, height=8, thick=2, gate=True, rng=rng))
    elif t in ("castle", "robber"):
        crecs, _ = S.castle(w, x0 + 4, g, rng, size="castle")
        recs.extend(crecs)
    elif t == "monastery":
        recs.append(S.wall_tower(w, x0 + 2, g, height=6, thick=1, gate=True, battlement=False, rng=rng))
        recs.append(S.church(w, x0 + 8, g, width=19, rng=rng))
        recs.append(S.house(w, x0 + 32, g, width=14, height=4, style="stone", rng=rng, kind="cloister"))
        recs.append(S.well(w, x0 + 50, g, rng=rng))
        workbench(w, x0 + 47, g)
        recs.append(S.field(w, x0 + 54, x0 + 70, g, rng))
        recs.append(S.wall_tower(w, x1 - 4, g, height=6, thick=1, gate=True, battlement=False, rng=rng))
    elif t == "mine":
        recs.append(S.house(w, x0 + 6, g, width=9, height=4, style=style, rng=rng, kind="house"))
        h = S.house(w, x0 + 18, g, width=8, height=4, style=style, rng=rng, kind="smithy")
        smithy_fittings(w, h)
        recs.append(h)
        S.mine_shaft(w, x0 + 32, g, 60, rng)
        recs.append(dict(kind="mine", x0=x0 + 32, x1=x0 + 34, g=g, door=x0 + 33, beds=[], work=x0 + 33, style="mine",
                         top=g - 3))
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
        sx = shore + side
        while 0 < sx < w.w - 1 and w.water_level(sx * TILE + 8) is None:
            sx += side
        recs.append(S.dock(w, sx - side * 4, SEA_LEVEL, 26, side, rng))
        workbench(w, (x0 + x1) // 2, g)
    # street lamps
    for r in recs:
        if r and r["kind"] in ("house", "tavern", "townhall", "kontor") and rng.random() < 0.5:
            tx = (r["x1"] + 1) * TILE + 8
            if w.water_level(tx) is None:
                w.index_add("decor_chunks", tx, Decor("torchpost", tx, g * TILE, 6, 34))
    return [r for r in recs if r]


def smithy_fittings(w, h):
    b = S.building(w, h["bid"])
    for kind, dx, ww, hh in (("anvil", 2.5, 18, 12), ("forge", 4.2, 24, 22)):
        d = Decor(kind, (h["x0"] + dx) * TILE, h["g"] * TILE, ww, hh, bld=b.id)
        b.decor.append(d)
        w.index_add("decor_chunks", d.x, d)
    b.lights.append(((h["x0"] + 4.2) * TILE, h["g"] * TILE - 14, 1.0))


def workbench(w, x, g):
    """A carpenter's bench in the open: the place to shape wood carefully (the workshop)."""
    px = x * TILE + 8
    w.index_add("decor_chunks", px, Decor("workbench", px, g * TILE, 34, 18))
