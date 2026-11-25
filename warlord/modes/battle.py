"""Feldschlacht — set-piece battles on small purpose-built maps.

Scenarios show off the formation system: hold a ford, defend a mountain gate (Klause),
an open-field clash of knights and pikes, and storming a castle.
"""
import random

import numpy as np
import pygame

from ..settings import TILE, SCREEN_W, WORLD_H, SEA_LEVEL, GOLD
from ..world import tiles as T
from ..world import structures as S
from ..world.world import World
from ..world.noise import fbm1
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
                  mine=[("schild", 30), ("speer", 28), ("armbrust", 20), ("bauern", 30)],
                  theirs=[("bogen", 18), ("schild", 22), ("raeuber", 30)],
                  intro=["The [Raubritter|robber knight] Kuno sits in his [Burg|castle] at Schwarzfels.",
                         "Order [Angriff|charge] and your men hack down the [Tor|gate] — or dig under the wall "
                         "until it collapses.",
                         "Raise [Schilde|shields] against the archers on the battlements."]),
}


def make_arena(kind, seed=7):
    rng = random.Random(seed)
    W = 960
    w = World(W, WORLD_H, seed)
    sc = SCENARIOS[kind]
    xs = np.arange(W, dtype=np.float32)
    h = 100 + (fbm1(xs, 1 / 60.0, seed, 3) - 0.5) * 6
    if kind == "pass":
        h = 100 - np.clip(np.abs(xs - W / 2) - 70, 0, None) * 0.35 + (fbm1(xs, 1 / 30.0, seed, 3) - 0.5) * 8
        h = np.maximum(h, 40)
    surf = h.astype(np.int32)
    if kind == "ford":
        c = W // 2
        for x in range(c - 30, c + 30):
            t = 1 - abs(x - c) / 30
            surf[x] += int(5 * t)
    w.surface[:] = surf
    ys = np.arange(WORLD_H)[None, :]
    depth = ys - surf[:, None]
    fg = np.zeros((W, WORLD_H), dtype=np.uint8)
    fg[depth >= 0] = T.STONE.id
    fg[(depth >= 0) & (depth < 6)] = T.DIRT.id
    top = T.GRASS.id if sc["biome"] != "mountains" else T.GRASS.id
    fg[depth == 0] = top
    fg[:, WORLD_H - 3:] = T.BEDROCK.id
    w.fg[:] = fg
    w.bg[depth >= 3] = T.BG_DIRT
    w.regions = [(0, W, sc["biome"])]
    w.abyss_w = -10
    if kind == "ford":
        c = W // 2
        lvl = int(surf[c - 34])
        for x in range(c - 30, c + 30):
            if surf[x] > lvl:
                w.liq[x, lvl:surf[x]] = 8
    # trees at the edges
    for x in list(range(10, 160, 9)) + list(range(W - 160, W - 10, 9)):
        if rng.random() < 0.6:
            from ..world.generator import grow_tree
            grow_tree(w, x, int(surf[x]), "oak" if sc["biome"] != "mountains" else "pine", rng)
    for x in range(W):
        if rng.random() < 0.2 and w.fg[x, surf[x] - 1] == 0:
            w.fg[x, surf[x] - 1] = T.TALLGRASS.id
    if kind == "pass":
        g = int(surf[W // 2])
        S.wall_tower(w, W // 2, g, height=10, thick=3, gate=True)
        S.tower(w, W // 2 - 7, g, width=6, height=13)
    if kind == "siege":
        g = int(np.median(surf[600:760]))
        surf[590:770] = g
        w.surface[:] = surf
        for x in range(590, 770):
            w.fg[x, :g] = 0
            w.fg[x, g:g + 6] = T.DIRT.id
            w.fg[x, g] = T.GRASS.id
        S.castle(w, 600, g, rng, size="castle")
    return w


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
        elif self.kind == "siege":
            x = 420 * TILE
            for unit, n in sc["mine"]:
                hf = Haufen(s, "player", unit, n, x, 1, mine_colors, leader=p)
                hf.order = "halt"
                s.formations.append(hf)
                p.haufen.append(hf)
                x -= hf.width() + 30
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
        if self.kind == "siege":
            # archers on the walls, men-at-arms in the courtyard, rabble outside the gate
            placements = [("bogen", 18, 612 * TILE), ("schild", 22, 640 * TILE), ("raeuber", 30, 560 * TILE)]
            for unit, n, px in placements:
                hf = Haufen(s, sc["enemy"], unit, n, px, -1, enemy_colors)
                hf.order = "halt"
                hf.no_advance = unit != "raeuber"
                s.formations.append(hf)
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
        s.ui.show_card(sc["de"], sc["intro"] + ["", "C = [Befehle|orders] · Tab = select · H = help",
                                               "Enemy waits until you advance — or until the horn sounds."],
                       subtitle=f"({sc['en']})", on_close=self.horn)

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
        text(surf, "C = Befehle (orders) · Tab = Auswahl (select)", (r.centerx, r.y + 26), 11, (190, 190, 180),
             center=True)


def build_battle(app, kind):
    from .session import Session
    w = make_arena(kind)
    spawn = {"pass": w.w // 2 - 30, "siege": 430}.get(kind, 395)
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
