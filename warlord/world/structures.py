"""Procedural architecture: huts, Fachwerk houses, churches, mills, walls, towers, castles, docks.

Every builder writes straight into the world layers and returns a building record that
NPC society uses (homes, workplaces, beds, doors...).

Convention: `g` is the ground row (the row of the floor tile). People stand on row g, i.e.
their feet are at pixel y = g * TILE. Interiors occupy rows g-h .. g-1.
"""
import random

from . import tiles as T


def _put(w, x, y, tid):
    if 0 <= x < w.w and 0 <= y < w.h:
        w.fg[x, y] = tid


def _bg(w, x, y, bid):
    if 0 <= x < w.w and 0 <= y < w.h:
        w.bg[x, y] = bid


def clear_box(w, x0, x1, y0, y1):
    """Clear fg and liquids in an inclusive box."""
    x0, x1 = max(0, x0), min(w.w - 1, x1)
    y0, y1 = max(0, y0), min(w.h - 1, y1)
    w.fg[x0:x1 + 1, y0:y1 + 1] = 0
    w.liq[x0:x1 + 1, y0:y1 + 1] = 0


def foundation(w, x0, x1, g, depth=4, tid=T.STONE.id):
    """Make sure there is solid ground under a footprint."""
    for x in range(x0, x1 + 1):
        for y in range(g, g + depth):
            if 0 <= x < w.w and 0 <= y < w.h and not T.SOLID[w.fg[x, y]]:
                w.fg[x, y] = tid


def roof(w, x0, x1, top, mat, overhang=1):
    """Triangular gable roof whose bottom row is `top`, spanning x0-overhang..x1+overhang."""
    a, b, y = x0 - overhang, x1 + overhang, top
    while a <= b:
        for x in range(a, b + 1):
            _put(w, x, y, mat)
        a += 1
        b -= 1
        y -= 1
    return y + 1


def house(w, x0, g, width=9, height=4, style="peasant", door_side=1, rng=None, kind="house"):
    rng = rng or random
    x1 = x0 + width - 1
    wall = {"peasant": T.FACHWERK.id, "burgher": T.FACHWERK.id, "stone": T.BRICK.id,
            "wood": T.PLANKS.id, "snow": T.PLANKS.id, "ash": T.BRICK.id}[style]
    mat = {"peasant": T.THATCH.id, "burgher": T.ROOFTILE.id, "stone": T.SLATE.id, "wood": T.THATCH.id,
           "snow": T.SLATE.id, "ash": T.SLATE.id}[style]
    bgw = {"peasant": T.BG_FACHWERK, "burgher": T.BG_FACHWERK, "stone": T.BG_BRICK, "wood": T.BG_PLANKS,
           "snow": T.BG_PLANKS, "ash": T.BG_BRICK}[style]
    floors = 2 if style == "burgher" and width >= 9 else 1
    total_h = height * floors + (floors - 1)
    clear_box(w, x0 - 2, x1 + 2, g - total_h - width // 2 - 4, g - 1)
    foundation(w, x0 - 1, x1 + 1, g)
    for x in range(x0, x1 + 1):
        _put(w, x, g, T.PLANKS.id if style != "stone" else T.COBBLE.id)
    top = g - total_h - 1
    for y in range(top + 1, g):
        _put(w, x0, y, wall)
        _put(w, x1, y, wall)
        for x in range(x0 + 1, x1):
            _bg(w, x, y, bgw)
    # windows
    for y in range(g - height + 1, g - 1, 3):
        for x in range(x0 + 2, x1 - 1, 3):
            _bg(w, x, y, T.BG_WINDOW)
    # upper floors as walkable platforms with a ladder
    ladder_x = x0 + 1 if door_side == 1 else x1 - 1
    for f in range(1, floors):
        fy = g - f * (height + 1)
        for x in range(x0 + 1, x1):
            _put(w, x, fy, T.PLATFORM.id)
        for y in range(fy, g):
            _put(w, ladder_x, y, T.LADDER.id)
        for y in range(fy - height + 1, fy - 1, 3):
            for x in range(x0 + 2, x1 - 1, 3):
                _bg(w, x, y, T.BG_WINDOW)
    for x in range(x0, x1 + 1):
        _put(w, x, top, T.PLANKS.id)
    roof(w, x0, x1, top - 1, mat)
    # doors (3 tall) on both sides: in a side view the street runs *through* the houses
    dx = x1 if door_side == 1 else x0
    for y in range(g - 3, g):
        _put(w, x0, y, T.DOOR.id)
        _put(w, x1, y, T.DOOR.id)
    # furniture
    inner = list(range(x0 + 1, x1))
    bed_x = x1 - 1 if door_side == -1 else x0 + 1
    if bed_x == ladder_x and floors > 1:
        bed_x = x0 + 2 if door_side == 1 else x1 - 2
    _put(w, bed_x, g - 1, T.BED.id)
    beds = [bed_x]
    spots = [x for x in inner if x not in (bed_x, ladder_x)]
    if spots:
        _put(w, spots[len(spots) // 2], g - 1, T.TABLE.id)
    if len(spots) > 2:
        _put(w, spots[-1] if door_side == -1 else spots[0], g - 1, T.CHEST.id)
        w.chests[(spots[-1] if door_side == -1 else spots[0], g - 1)] = {"bread": rng.randint(0, 2),
                                                                        "wheat": rng.randint(0, 3)}
    if floors > 1:
        fy = g - (height + 1)
        _put(w, x0 + width // 2, fy - 1, T.BED.id)
        beds.append(x0 + width // 2)
    return dict(kind=kind, x0=x0, x1=x1, g=g, door=dx, beds=beds, work=x0 + width // 2, style=style,
                top=top - width // 2 - 1)


def church(w, x0, g, width=13, rng=None):
    x1 = x0 + width - 1
    h = 7
    clear_box(w, x0 - 3, x1 + 3, g - h - 22, g - 1)
    foundation(w, x0 - 1, x1 + 1, g)
    for x in range(x0, x1 + 1):
        _put(w, x, g, T.COBBLE.id)
    top = g - h - 1
    for y in range(top + 1, g):
        _put(w, x0, y, T.BRICK.id)
        _put(w, x1, y, T.BRICK.id)
        for x in range(x0 + 1, x1):
            _bg(w, x, y, T.BG_BRICK)
    for x in range(x0 + 2, x1 - 1, 2):
        for y in range(g - 5, g - 2):
            _bg(w, x, y, T.BG_WINDOW)
    for x in range(x0, x1 + 1):
        _put(w, x, top, T.BRICK.id)
    roof(w, x0, x1, top - 1, T.SLATE.id)
    # bell tower over the west end
    tx0, tx1 = x0, x0 + 3
    ttop = top - 12
    for y in range(ttop, top):
        _put(w, tx0, y, T.BRICK.id)
        _put(w, tx1, y, T.BRICK.id)
        for x in range(tx0 + 1, tx1):
            _bg(w, x, y, T.BG_BRICK)
            _put(w, x, y, 0)
    _put(w, tx0 + 1, ttop + 2, T.BELL.id)
    for x in range(tx0, tx1 + 1):
        _put(w, x, ttop, T.BRICK.id)
    a, b, y = tx0, tx1, ttop - 1
    for k in range(6):
        for x in range(a + (k // 2), b - (k // 2) + 1):
            _put(w, x, y - k, T.SLATE.id)
    for y in range(g - 3, g):
        _put(w, x1, y, T.DOOR.id)
        _put(w, x0, y, T.DOOR.id)
    _put(w, x0 + 2, g - 1, T.ALTAR.id)
    for x in range(x0 + 5, x1 - 1, 2):
        _put(w, x, g - 1, T.TABLE.id)  # pews
    return dict(kind="church", x0=x0, x1=x1, g=g, door=x1, beds=[], work=x0 + 2, style="stone", top=ttop - 6)


def windmill(w, x0, g):
    """A post mill: the sails are a dynamic entity (driven by the wind) placed by the game."""
    x1 = x0 + 4
    clear_box(w, x0 - 2, x1 + 2, g - 12, g - 1)
    foundation(w, x0, x1, g)
    for y in range(g - 8, g):
        _put(w, x0, y, T.PLANKS.id)
        _put(w, x1, y, T.PLANKS.id)
        for x in range(x0 + 1, x1):
            _bg(w, x, y, T.BG_PLANKS)
    for x in range(x0, x1 + 1):
        _put(w, x, g - 9, T.PLANKS.id)
        _put(w, x, g, T.PLANKS.id)
    roof(w, x0, x1, g - 10, T.THATCH.id, overhang=0)
    for y in range(g - 3, g):
        _put(w, x1, y, T.DOOR.id)
        _put(w, x0, y, T.DOOR.id)
    _put(w, x0 + 2, g - 1, T.BARREL.id)
    return dict(kind="mill", x0=x0, x1=x1, g=g, door=x1, beds=[], work=x0 + 2, style="wood", top=g - 12,
                hub=(x0 + 2, g - 7))


def well(w, x, g):
    clear_box(w, x - 1, x + 1, g - 3, g - 1)
    _put(w, x, g - 1, T.WELL.id)
    return dict(kind="well", x0=x, x1=x, g=g, door=x, beds=[], work=x, style="stone", top=g - 3)


def field(w, x0, x1, g, rng):
    for x in range(x0, x1 + 1):
        clear_box(w, x, x, g - 3, g - 1)
        _put(w, x, g, T.FARMLAND.id)
        if rng.random() < 0.9:
            _put(w, x, g - 1, rng.choice(T.CROP_STAGES))
    return dict(kind="field", x0=x0, x1=x1, g=g, door=x0, beds=[], work=(x0 + x1) // 2, style="field", top=g - 2)


def stall(w, x0, g, rng):
    clear_box(w, x0, x0 + 3, g - 5, g - 1)
    for x in range(x0, x0 + 4):
        _put(w, x, g - 4, T.PLATFORM.id)
        _put(w, x, g, T.COBBLE.id)
    _put(w, x0 + 1, g - 1, T.STALL.id)
    _put(w, x0 + 2, g - 1, T.BARREL.id)
    return dict(kind="stall", x0=x0, x1=x0 + 3, g=g, door=x0, beds=[], work=x0 + 1, style="market", top=g - 5)


def palisade(w, x, g, height=5):
    clear_box(w, x, x, g - height - 1, g - 1)
    for y in range(g - height, g):
        _put(w, x, y, T.PALISADE.id)
    foundation(w, x, x, g)


def wall_tower(w, x0, g, height=10, thick=2, gate=True, battlement=True, mat=T.BRICK.id):
    """A stretch of curtain wall with optional gate (3 tall)."""
    x1 = x0 + thick - 1
    clear_box(w, x0 - 1, x1 + 1, g - height - 2, g - 1)
    foundation(w, x0, x1, g, depth=6)
    for x in range(x0, x1 + 1):
        for y in range(g - height, g):
            _put(w, x, y, mat)
            _bg(w, x, y, T.BG_BRICK)
    if battlement:
        for x in range(x0 - 1, x1 + 2):
            _put(w, x, g - height - 1, mat if (x - x0) % 2 == 0 else 0)
            _put(w, x, g - height, mat)
    gate_x = []
    if gate:
        for x in range(x0, x1 + 1):
            for y in range(g - 3, g):
                _put(w, x, y, T.GATE.id)
            gate_x.append(x)
    # ladder on the inner side for defenders
    return dict(kind="wall", x0=x0, x1=x1, g=g, door=x0, beds=[], work=x0, style="stone", top=g - height - 1,
                gate=gate_x)


def tower(w, x0, g, width=7, height=16, mat=T.BRICK.id, roofmat=T.SLATE.id):
    x1 = x0 + width - 1
    clear_box(w, x0 - 1, x1 + 1, g - height - 8, g - 1)
    foundation(w, x0, x1, g, depth=6)
    top = g - height
    for y in range(top, g):
        _put(w, x0, y, mat)
        _put(w, x1, y, mat)
        for x in range(x0 + 1, x1):
            _bg(w, x, y, T.BG_BRICK)
    for x in range(x0, x1 + 1):
        _put(w, x, top, mat)
        _put(w, x, g, T.COBBLE.id)
    # floors with ladders
    for fy in range(g - 5, top, -5):
        for x in range(x0 + 1, x1):
            _put(w, x, fy, T.PLATFORM.id)
        _put(w, x0 + 1, fy - 2, T.TORCH.id)
    for y in range(top + 1, g):
        _put(w, x0 + 1 + (width - 3) // 2, y, T.LADDER.id)
    for y in range(top - 1, top + 1):
        pass
    # battlements
    for x in range(x0 - 1, x1 + 2):
        _put(w, x, top - 1, mat if (x - x0) % 2 == 0 else 0)
    if roofmat:
        a, b = x0, x1
        y = top - 3
        k = 0
        while a <= b:
            for x in range(a, b + 1):
                _put(w, x, y, roofmat)
            k += 1
            if k % 2 == 0:
                a += 1
                b -= 1
            y -= 1
    for y in range(g - 3, g):
        _put(w, x1, y, T.DOOR.id)
        _put(w, x0, y, T.DOOR.id)
    return dict(kind="tower", x0=x0, x1=x1, g=g, door=x1, beds=[], work=x0 + width // 2, style="stone",
                top=top - 10)


def great_hall(w, x0, g, width=17, height=6):
    x1 = x0 + width - 1
    clear_box(w, x0 - 2, x1 + 2, g - height - width // 2 - 3, g - 1)
    foundation(w, x0, x1, g, depth=5)
    top = g - height - 1
    for y in range(top + 1, g):
        _put(w, x0, y, T.BRICK.id)
        _put(w, x1, y, T.BRICK.id)
        for x in range(x0 + 1, x1):
            _bg(w, x, y, T.BG_TAPESTRY if (x // 3) % 2 == 0 else T.BG_BRICK)
    for x in range(x0, x1 + 1):
        _put(w, x, top, T.BRICK.id)
        _put(w, x, g, T.COBBLE.id)
    roof(w, x0, x1, top - 1, T.SLATE.id)
    for y in range(g - 3, g):
        _put(w, x0, y, T.DOOR.id)
        _put(w, x1, y, T.DOOR.id)
    _put(w, x1 - 3, g - 1, T.THRONE.id)
    for x in range(x0 + 2, x1 - 3, 4):
        _put(w, x, g - 4, T.BANNER.id)
        _put(w, x + 1, g - 3, T.TORCH.id)
    for x in range(x0 + 4, x1 - 4):
        _put(w, x, g - 1, T.TABLE.id)
    return dict(kind="hall", x0=x0, x1=x1, g=g, door=x0, beds=[x0 + 2], work=x1 - 2, style="stone",
                top=top - width // 2)


def castle(w, x0, g, rng, size="castle"):
    """Curtain walls + keep + great hall + towers. Returns (records, x1)."""
    recs = []
    inner = 46 if size == "castle" else 64
    x = x0
    recs.append(tower(w, x, g, width=6, height=14))
    x += 6
    recs.append(wall_tower(w, x, g, height=9, thick=2, gate=True))
    x += 2
    # courtyard
    keep_x = x + 3
    recs.append(tower(w, keep_x, g, width=9, height=22))
    recs[-1]["kind"] = "keep"
    hall_x = keep_x + 12
    recs.append(great_hall(w, hall_x, g, width=17))
    cur = hall_x + 20
    if size != "castle":
        h = house(w, cur, g, width=9, height=4, style="stone", rng=rng, kind="barracks")
        recs.append(h)
        cur += 11
    smith = house(w, cur, g, width=8, height=4, style="stone", rng=rng, kind="smithy")
    _put(w, smith["x0"] + 3, g - 1, T.ANVIL.id)
    _put(w, smith["x0"] + 2, g - 1, T.FORGE.id)
    recs.append(smith)
    end = x + inner
    end = max(end, cur + 10)
    # wall walk platforms between towers so archers can man the walls
    for xx in range(x0 + 6, end + 2):
        if w.fg[xx, g - 10] == 0:
            pass
    recs.append(wall_tower(w, end, g, height=9, thick=2, gate=True))
    recs.append(tower(w, end + 2, g, width=6, height=14))
    # courtyard paving
    for xx in range(x0, end + 8):
        if w.fg[xx, g] not in (T.BRICK.id,):
            _put(w, xx, g, T.COBBLE.id)
    return recs, end + 8


def dock(w, shore_x, g_water, length, direction, rng):
    """Planks over water with posts down to the seabed. direction: +1 east, -1 west."""
    xs = [shore_x + direction * i for i in range(length)]
    y = g_water - 1
    for x in xs:
        if not (0 <= x < w.w):
            continue
        _put(w, x, y, T.PLATFORM.id)
        w.liq[x, y] = 0
        if (x - shore_x) % 5 == 0:
            yy = y + 1
            while yy < w.h - 1 and not T.SOLID[w.fg[x, yy]]:
                _put(w, x, yy, T.LOG.id)
                yy += 1
    end = xs[-1]
    _put(w, xs[2], y - 1, T.BARREL.id)
    _put(w, xs[-2], y - 1, T.TORCH.id)
    return dict(kind="dock", x0=min(xs), x1=max(xs), g=y, door=xs[2], beds=[], work=end, style="wood",
                top=y - 2, berth=end + direction * 6)


def shipwreck(w, x0, g, rng):
    for i in range(14):
        x = x0 + i
        yb = g - (1 if 2 < i < 11 else 2)
        _put(w, x, yb, T.WRECK.id)
        if i in (0, 13):
            for y in range(g - 5, g):
                _put(w, x, y, T.WRECK.id)
    for y in range(g - 9, g - 1):
        if rng.random() < 0.8:
            _put(w, x0 + 6, y, T.WRECK.id)
    _put(w, x0 + 4, g - 2, T.CHEST.id)
    w.chests[(x0 + 4, g - 2)] = {"silver_coin": rng.randint(20, 60), "rope": 2, "iron_ingot": rng.randint(1, 4)}


def mine_shaft(w, x, g, depth, rng):
    for y in range(g - 2, g + depth):
        for xx in (x, x + 1, x + 2):
            if 0 <= y < w.h:
                w.fg[xx, y] = 0
                w.liq[xx, y] = 0
                w.bg[xx, y] = T.BG_PLANKS if y > g else w.bg[xx, y]
        _put(w, x + 1, y, T.LADDER.id)
    for k in range(g + 8, g + depth, 10):
        direction = rng.choice((-1, 1))
        for i in range(3, 40):
            xx = x + 1 + direction * i
            for y in range(k - 3, k):
                _put(w, xx, y, 0)
                _bg(w, xx, y, T.BG_STONE)
                w.liq[xx, y] = 0
            if i % 8 == 0:
                _put(w, xx, k - 3, T.TORCH.id)
            if i % 4 == 0 and rng.random() < 0.5:
                for yy in (k, k - 4):
                    _put(w, xx, yy, rng.choice((T.IRON.id, T.COAL.id, T.SILVER.id)))
