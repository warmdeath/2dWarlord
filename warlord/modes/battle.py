"""Feldschlacht — set-piece battles on small purpose-built maps.

Scenarios show off the formation system: hold a ford, defend a mountain gate (Klause),
an open-field clash of knights and pikes, and storming a castle.
"""
import random

import numpy as np
import pygame

from ..settings import TILE, SCREEN_W, WORLD_H, SEA_LEVEL, GOLD
from ..world.noise import fbm1
from ..poly.world import PolyWorld, Water
from ..poly import prefab as S
from ..poly.flora import Tree
from ..combat.formation import Haufen
from ..society.kingdoms import BY_KEY
from ..ui.common import text, panel, bilingual

SCENARIOS = {
    "ford": dict(de="Die Furt", en="The Ford", biome="forest", enemy="glutmark",
                 mine=[("speer", 30), ("schild", 22), ("bogen", 24)],
                 theirs=[("bauern", 40), ("speer", 34), ("schild", 26), ("bogen", 26), ("reisige", 10)],
                 intro=["Markgraf Otto's host must cross the [Furt|ford] to reach Heiligenstein.",
                        "Water slows every step. Let your [Bogenschützen|archers] shoot while they wade,",
                        "then meet them at the bank with [Speere|spears] and a [Schildwall|shield wall]."]),
    "pass": dict(de="Die Klause", en="The Pass", biome="mountains", enemy="glutmark",
                 mine=[("schild", 26), ("armbrust", 18)],
                 theirs=[("bauern", 60), ("speer", 40), ("schild", 30), ("armbrust", 22)],
                 intro=["A stone [Tor|gate] closes the only pass through the mountains.",
                        "Few against many: they must hack through the gate before they can fight you.",
                        "Rotate your front rank with [Wechsel|switch] so fresh men always hold the breach."]),
    "field": dict(de="Offene Feldschlacht", en="Open Battle", biome="hills", enemy="waldheim",
                  mine=[("spiess", 40), ("schild", 24), ("bogen", 26), ("ritter", 10)],
                  theirs=[("ritter", 14), ("reisige", 12), ("speer", 34), ("bogen", 30), ("schild", 20)],
                  intro=["Duke Eberhard's [Ritter|knights] will charge. Their charge breaks anything —",
                         "except a [Igel|hedgehog] of braced pikes. Keep your archers behind the pikes,",
                         "and send your own knights against their archers."]),
    "siege": dict(de="Die Belagerung", en="The Siege", biome="forest", enemy="bandit",
                  mine=[("schild", 26), ("leiter", 22), ("mineure", 12), ("armbrust", 20)],
                  engines=[("ramm", 548), ("turm", 530), ("blide", 505)],
                  intro=["The [Raubritter|robber knight] Kuno sits behind a [Graben|moat], a [Zugbrücke|drawbridge] "
                         "and an iron [Fallgatter|portcullis].",
                         "Your [Blide|trebuchet] batters the walls. Your [Rammbock|ram] needs the moat filled first —",
                         "men stuck below a bank shovel a [Rampe|ramp]. [Leiterträger|ladder men] climb, the "
                         "[Belagerungsturm|siege tower] brings your shields onto the wall,",
                         "and the [Mineure|sappers] dig under it and burn the props.",
                         "X = orders (Vorwärts!) · E next to an engine starts or stops it."]),
    "verteidigung": dict(de="Die Verteidigung", en="The Defence", biome="hills", enemy="glutmark",
                         mine=[("bogen", 14), ("armbrust", 12), ("schild", 24), ("hellebarde", 16)],
                         theirs=[("leiter", 26), ("schild", 30), ("bauern", 40), ("mineure", 14), ("armbrust", 20)],
                         engines=[("ramm", 470), ("turm", 440), ("blide", 500), ("buechse", 548), ("buechse", 540)],
                         intro=["Markgraf Otto der Rote brings fire against your [Burg|castle] — and something new:",
                                "two [Donnerbüchsen|thunder-guns] that spit iron with a roar. They may burst. Pray "
                                "they do.",
                                "Archers on the towers, [Hellebardiere|halberdiers] at the gate. Push the "
                                "[Leitern|ladders] off the wall,",
                                "pour [Pech|pitch] from the [Pechnase|machicolation] (E on the tower top) on whoever "
                                "reaches the gate,",
                                "and burn the siege tower with fire arrows (V)."]),
}


def make_arena(kind, seed=7):
    rng = random.Random(seed)
    W = 960
    w = PolyWorld(W, WORLD_H, seed)
    sc = SCENARIOS[kind]
    xs = np.arange(W + 1, dtype=np.float32)
    h = 100 + (fbm1(xs, 1 / 60.0, seed, 3) - 0.5) * 6
    if kind == "pass":
        h = 100 - np.clip(np.abs(xs - W / 2) - 70, 0, None) * 0.35 + (fbm1(xs, 1 / 30.0, seed, 3) - 0.5) * 8
        h = np.maximum(h, 40)
    if kind == "ford":
        c = W // 2
        t = np.clip(1 - np.abs(xs - c) / 30, 0, 1)
        h = h + 5 * t
    if kind in ("siege", "verteidigung"):
        g = int(np.median(h[600:760]))
        h[586:774] = g
        for i in range(1, 25):
            f = i / 25
            h[586 - i] = g * (1 - f) + h[586 - i] * f
            h[773 + i] = g * (1 - f) + h[773 + i] * f
    w.top[:] = (h * TILE).astype(np.float32)
    w.surface[:] = np.round(h[:W]).astype(np.int32)
    w.bottom[:] = (WORLD_H - 2) * TILE
    w.regions = [(0, W, sc["biome"])]
    w.abyss_w = -10
    if kind == "ford":
        c = W // 2
        lvl = float(h[c - 34]) * TILE
        w.water.append(Water((c - 30) * TILE, (c + 30) * TILE, lvl, False))
    # woods at the edges
    for x in list(range(10, 160, 7)) + list(range(W - 160, W - 10, 7)):
        if rng.random() < 0.6:
            px = x * TILE + rng.uniform(0, TILE)
            kind_t = "oak" if sc["biome"] != "mountains" else "pine"
            if sc["biome"] == "forest" and rng.random() < 0.4:
                kind_t = rng.choice(["beech", "birch", "pine"])
            hgt = rng.uniform(150, 240)
            t = Tree(kind_t, px, w.surface_y(px) + 3, hgt, 13 * (hgt / 190) ** 0.7, rng.randint(0, 1 << 30))
            w.trees.append(t)
            w.index_add("tree_chunks", px, t)
    for x in range(0, W, 3):
        if rng.random() < 0.15:
            px = x * TILE
            w.index_add("decor_chunks", px, S.Decor(rng.choice(["bush", "flowers", "fern"]), px, w.surface_y(px) + 2,
                                                     14, 12, seed=rng.randint(0, 9999)))
    if kind == "pass":
        g = int(h[W // 2])
        S.wall_tower(w, W // 2, g, height=10, thick=3, gate=True, rng=rng)
        S.tower(w, W // 2 - 7, g, width=6, height=13, rng=rng)
    if kind in ("siege", "verteidigung"):
        g = int(np.median(h[600:760]))
        S.castle(w, 600, g, rng, size="castle")
        w.castle_g = g
        for gh in w.gatehouses:
            gh.owner = "player" if kind == "verteidigung" else sc["enemy"]
            gh.auto = True
            gh.pitch = 8
    return w


def top_of(w, tx):
    """The highest walkable surface above column tx (a tower top, a wall walk)."""
    px = tx * TILE + 8
    return w.ground_y(px, w.surface_y(px) - 700, 760)


class Battle:
    def __init__(self, session, kind):
        self.s = session
        self.kind = kind
        self.sc = SCENARIOS[kind]
        self.enemy_sides = {self.sc["enemy"]}
        self.t = 0.0
        self.over = False
        self.result = None
        self.start_counts = None

    def setup(self):
        s = self.s
        w = s.world
        sc = self.sc
        p = s.player
        mine_colors = ((40, 70, 140), (236, 232, 222))
        enemy_colors = BY_KEY[sc["enemy"]]["colors"] if sc["enemy"] in BY_KEY else ((50, 44, 40), (180, 30, 30))
        if self.kind == "pass":
            x = (w.w // 2 - 4) * TILE
            for unit, n in sc["mine"]:
                hf = Haufen(s, "player", unit, n, x, 1, mine_colors, leader=p)
                hf.order = "halt"
                s.formations.append(hf)
                p.haufen.append(hf)
                x -= hf.width() + 30
            ex = (w.w // 2 + 60) * TILE
        elif self.kind in ("siege", "verteidigung"):
            ex = None
        else:
            x = 380 * TILE
            for unit, n in sc["mine"]:
                hf = Haufen(s, "player", unit, n, x, 1, mine_colors, leader=p)
                hf.order = "halt"
                s.formations.append(hf)
                p.haufen.append(hf)
                x -= hf.width() + 30
            ex = 600 * TILE
        if self.kind in ("siege", "verteidigung"):
            self.setup_siege(mine_colors, enemy_colors)
        else:
            order = sorted(sc["theirs"], key=lambda u: (u[0] in ("bogen", "armbrust"),))
            for unit, n in order:
                hf = Haufen(s, sc["enemy"], unit, n, ex, -1, enemy_colors)
                hf.order = "halt"
                s.formations.append(hf)
                ex += hf.width() + 30
        p.selected_haufen = -1
        for h in p.haufen:
            h.selected = True
        self.start_counts = (sum(h.count for h in p.haufen), sum(h.count for h in s.formations if h.side != "player"))
        s.ui.show_card(sc["de"], sc["intro"] + ["", "X = [Befehle|orders] · Tab = select · H = help",
                                               "Enemy waits until you advance — or until the horn sounds."],
                       subtitle=f"({sc['en']})", on_close=self.horn)

    def setup_siege(self, mine_colors, enemy_colors):
        """The castle at tiles 600-662: west tower 600-605, gate wall 606-607, keep 611-619, hall, east wall."""
        from ..entities.humanoid import Humanoid
        from ..society.names import make_look
        s = self.s
        w = s.world
        sc = self.sc
        p = s.player
        g = w.castle_g
        defenders_side = "player" if self.kind == "verteidigung" else sc["enemy"]
        dcol = mine_colors if defenders_side == "player" else enemy_colors
        acol = enemy_colors if defenders_side == "player" else mine_colors
        attackers_side = sc["enemy"] if defenders_side == "player" else "player"
        top = top_of(w, 603)

        w.stream(620 * TILE, 3000)

        def garrison(unit, n, x, row, no_adv=True, side=defenders_side, col=dcol, facing=-1):
            hf = Haufen(s, side, unit, n, x * TILE + 6, facing, col, leader=p if side == "player" else None)
            hf.base_y = row if row > 500 else row * TILE
            hf.y_cache = {}
            hf.order = "halt"
            hf.no_advance = no_adv
            s.formations.append(hf)
            if side == "player":
                p.haufen.append(hf)
            return hf

        if self.kind == "verteidigung":
            garrison("bogen", sc["mine"][0][1], 600, top)
            garrison("armbrust", sc["mine"][1][1], 659, top_of(w, 661))
            garrison("hellebarde", sc["mine"][3][1], 610, g * TILE)
            garrison("schild", sc["mine"][2][1], 628, g * TILE)
        else:
            garrison("bogen", 12, 600, top)
            garrison("schild", 20, 628, g * TILE)
            garrison("raeuber", 26, 578, w.surface_y(578 * TILE), no_adv=False)
        # wall guards: individuals who man the battlements and shove ladders off
        for i, tx in enumerate((601, 603, 604, 606, 607, 608)):
            ty = top_of(w, tx)
            look = make_look(s.rng, 1, "guard", kingdom_colors=dcol, soldier=True)
            h = Humanoid(tx * TILE, ty - 43, look, defenders_side, "Burgwache")
            h.equip(weapon=s.rng.choice(["speer", "schwert", "axt"]), shield="holzschild", armor="gambeson",
                    helmet="eisenhut")
            h.leash = (tx * TILE + 8, 110)
            h.brave = True
            h.keep = True
            h.home_brain = "combat"
            s.add_humanoid(h, "combat")
        # the besiegers
        ax = 520 if self.kind == "siege" else 500
        army = sc["mine"] if self.kind == "siege" else sc["theirs"]
        tower_haufen = None
        x = ax * TILE
        for unit, n in army:
            hf = Haufen(s, attackers_side, unit, n, x, 1, acol, leader=p if attackers_side == "player" else None)
            hf.order = "halt"
            s.formations.append(hf)
            if attackers_side == "player":
                p.haufen.append(hf)
            if unit == "schild":
                tower_haufen = hf
            x -= hf.width() + 30
        for key, ex in sc["engines"]:
            e = s.spawn_engine(key, ex * TILE, attackers_side, 1, acol)
            e.active = False
            if key == "turm" and tower_haufen is not None:
                e.carry = tower_haufen
                tower_haufen.leader = e
                tower_haufen.order = "folgt"
        if self.kind == "siege":
            p.x = (ax - 70) * TILE
        else:
            p.x = 630 * TILE
        p.y = w.ground_y(p.cx, w.surface_y(p.cx) - 60, 200) - p.h - 1
        p.fall_peak = p.y
        s.camera.snap(p.cx, p.cy)
        p.inv.add("pech", 4)

    def horn(self):
        self.s.sfx("horn")
        self.started = True

    def on_event(self, name, kw):
        pass

    def update(self, dt):
        if self.over or not getattr(self, "started", False):
            return
        self.t += dt
        s = self.s
        if self.t > 4 and not getattr(self, "engines_go", False):
            self.engines_go = True
            for e in s.engines:
                e.active = True
            for hf in s.formations:
                if self.kind == "verteidigung" and hf.side != "player" and hf.order == "halt":
                    hf.order = "vorwaerts"
        # after a short pause the enemy begins its advance
        if self.t > 6:
            for hf in s.formations:
                if hf.side != "player" and hf.order == "halt" and not getattr(hf, "no_advance", False) and \
                        not hf.unit.ranged:
                    hf.order = "vorwaerts"
        mine = [h for h in s.formations if h.side == "player" and not h.routed]
        theirs = [h for h in s.formations if h.side != "player" and not h.routed]
        if not theirs and self.t > 3:
            self.finish(True)
        elif (not mine and self.t > 3) or s.player.dead:
            self.finish(False)

    def finish(self, won):
        self.over = True
        self.result = won
        s = self.s
        a, b = self.start_counts
        left_m = sum(h.count for h in s.formations if h.side == "player")
        left_t = sum(h.count for h in s.formations if h.side != "player")
        lines = [f"Your men: {a} → {left_m}", f"Enemy: {b} → {left_t}", "",
                 "[Sieg|victory]! [Gott mit uns|God with us]!" if won else
                 "[Niederlage|defeat]. Learn from it — then ride again."]
        s.sfx("bell" if won else "horn")
        s.ui.show_card("Sieg!" if won else "Niederlage", lines, on_close=s.app.to_menu,
                       subtitle="(victory)" if won else "(defeat)")

    def draw_hud(self, surf):
        s = self.s
        mine = sum(h.count for h in s.formations if h.side == "player")
        theirs = sum(h.count for h in s.formations if h.side != "player")
        r = panel(surf, (SCREEN_W // 2 - 170, 10, 340, 44), 170)
        text(surf, f"{self.sc['de']}  ·  Deine: {mine}  ⚔  Feinde: {theirs}", (r.centerx, r.y + 6), 15, GOLD,
             center=True)
        text(surf, "X = Befehle (orders) · Tab = Auswahl (select)", (r.centerx, r.y + 26), 11, (190, 190, 180),
             center=True)


def build_battle(app, kind):
    from .session import Session
    w = make_arena(kind)
    spawn = {"pass": w.w // 2 - 30, "siege": 450, "verteidigung": 630}.get(kind, 395)
    s = Session(app, w, mode="battle", seed=7, spawn=spawn, player_rank=6)
    p = s.player
    p.look["tabard"] = ((40, 70, 140), (236, 232, 222))
    p.look["trim"] = (214, 178, 74)
    for k, n in (("schwert", 1), ("bogen", 1), ("arrow", 40), ("spitzhacke", 1), ("bread", 5), ("armbrust", 1),
                 ("bolt", 20), ("verband", 5)):
        p.inv.add(k, n)
    p.equip(weapon="schwert", shield="dreieckschild", armor="kettenhemd", helmet="topfhelm")
    p.max_hp = p.hp = 160
    p.rank = 6
    s.sync_held()
    horse = s.spawn_horse(p.cx - 40, p.feet, wild=False)
    horse.owner = p
    s.env.time = 600 * 0.33
    s.env.force("klar" if kind != "pass" else "wolkig")
    s.battle = Battle(s, kind)
    s.battle.setup()
    return s
