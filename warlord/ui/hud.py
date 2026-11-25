"""In-game UI: HUD, speech bubbles, and all overlay screens."""
import math
import random

import numpy as np
import pygame

from ..settings import SCREEN_W, SCREEN_H, TILE, GOLD, PARCHMENT, INK, GERMAN_COLOR, SEA_LEVEL
from . import bagui
from .lab import Lab
from ..items.items import ITEMS
from ..items import crafting as CR
from ..items.blueprints import BLUEPRINTS
from ..society import dialogue as D
from ..society.ranks import RANKS, rank as rank_of
from ..society.kingdoms import KINGDOMS, BY_KEY, BIOME_NAMES
from ..combat.weapons import WEAPONS, SHIELDS, ARMORS, HELMET_NAMES
from ..combat.units import UNITS
from ..gfx.rig import draw_humanoid
from .common import font, text, panel, parchment, bilingual, bar, item_icon, ltext
from ..society import lingua

SELL_LISTS = {
    "merchant": ["bread", "cheese", "fish", "salt", "beer", "wine", "wood", "planks", "stone", "brick", "straw",
                 "rooftile", "slate", "clay", "rope", "cloth", "wool", "leather", "coal", "iron_ore", "iron_ingot",
                 "seeds", "torch", "arrow", "ladder", "door", "chest", "bed", "workbench", "boat"],
    "smith": ["schwert", "axt", "speer", "dolch", "streitkolben", "hellebarde", "spiess", "langschwert", "armbrust",
              "bogen", "lanze", "spitzhacke", "hammer", "sichel", "holzschild", "dreieckschild", "pavese", "gambeson",
              "kettenhemd", "plattenrock", "kettenhaube", "eisenhut", "beckenhaube", "topfhelm", "arrow", "bolt",
              "iron_ingot", "anvil"],
    "innkeeper": ["beer", "wine", "bread", "cheese", "meat", "fish"],
    "baker": ["bread", "flour", "wheat"],
    "fisher": ["fish", "rope", "boat"],
    "miller": ["flour", "wheat", "seeds"],
    "lord": ["horse", "lanze", "dreieckschild"],
    "ruler": ["horse"],
    "knight": ["horse"],
    "weaver": ["cloth", "wool", "rope", "gambeson"],
    "farmer": ["wheat", "seeds", "bread", "cheese"],
    "monk": ["wine", "bread", "herb"],
}
JOB_DE = {"farmer": ("Bauer", "farmer"), "smith": ("Schmied", "smith"), "miller": ("Müller", "miller"),
          "baker": ("Bäcker", "baker"), "fisher": ("Fischer", "fisher"), "woodcutter": ("Holzfäller", "woodcutter"),
          "weaver": ("Weber", "weaver"), "innkeeper": ("Wirt", "innkeeper"), "merchant": ("Händler", "merchant"),
          "guard": ("Wache", "guard"), "priest": ("Priester", "priest"), "monk": ("Mönch", "monk"),
          "child": ("Kind", "child"), "beggar": ("Bettler", "beggar"), "shepherd": ("Schäfer", "shepherd"),
          "miner": ("Bergmann", "miner"), "carter": ("Fuhrmann", "carter"), "potter": ("Töpfer", "potter"),
          "lord": ("Lehnsherr", "lord"), "knight": ("Ritter", "knight"), "ruler": ("Herrscher", "ruler"),
          "mayor": ("Bürgermeister", "mayor"), "bandit": ("Räuber", "robber"), "raubritter": ("Raubritter",
                                                                                             "robber knight")}


class UI:
    def __init__(self, game):
        self.g = game
        self.small = font(14)
        self.tiny = font(11)
        self.med = font(18)
        self.big = font(30, bold=True)
        self.toasts = []
        self.modal = None
        self.npc = None
        self.dlg_line = None
        self.dlg_opts = []
        self.scroll = 0
        self.build_sel = None
        self.order_bar = False
        self.fade_t = 0.0
        self.fade_text = ""
        self.card = None
        self.map_img = None
        self.quiz = None
        self.hover_tip = None
        self.recipe_scroll = 0
        self.trade_scroll = 0
        self.last_loc = None
        self.loc_t = 0.0

    # ------------------------------------------------------------------ state
    def modal_blocks(self):
        return self.modal in ("pause", "death", "card", "map", "woerterbuch", "stand", "help", "dialogue", "trade",
                              "inventory", "lab") or self.fade_t > 0.6

    def captures_input(self):
        return self.modal is not None or self.order_bar

    def toast(self, line, t=4.0):
        line = lingua.get().weave(line)
        self.toasts.append([line, t])
        self.toasts = self.toasts[-3:]

    def new_words(self, words):
        self.pending_words = getattr(self, "pending_words", []) + list(words)

    def flush_words(self, dt):
        self.word_t = getattr(self, "word_t", 0.0) - dt
        pw = getattr(self, "pending_words", [])
        if pw and self.word_t <= 0:
            shown = pw[:3]
            self.pending_words = pw[3:]
            self.word_t = 2.5
            label = "Neues Wort" if len(shown) == 1 else "Neue Wörter"
            self.toast(f"{label}: " + ", ".join(f"[{de}|{en}]" for de, en in shown), 3.5)

    def fade(self, line):
        self.fade_t = 2.2
        self.fade_text = line

    def death_screen(self):
        self.modal = "death"

    def open_lab(self, bench):
        self.lab = Lab(self, bench)
        self.modal = "lab"
        self.g.sfx("ui")

    def open(self, name):
        self.modal = name
        self.scroll = 0
        self.g.sfx("ui")

    def show_card(self, title, lines, on_close=None, subtitle=None):
        lines = [lingua.get().weave(x) for x in lines]
        self.card = {"title": title, "lines": lines, "on_close": on_close, "subtitle": subtitle}
        self.modal = "card"
        for line in lines:
            self.g.hear(line, "chronicle", toast=False)

    # ------------------------------------------------------------------ input
    def update(self, dt, events):
        g = self.g
        p = g.player
        self.fade_t = max(0.0, self.fade_t - dt)
        self.flush_words(dt)
        for t in self.toasts:
            t[1] -= dt
        self.toasts = [t for t in self.toasts if t[1] > 0]
        for e in events:
            if self.modal == "lab" and getattr(self, "lab", None) is not None:
                if e.type == pygame.KEYDOWN:
                    self.lab.key(e.key)
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button in (1, 3):
                    self.lab.mouse_down(e.pos, e.button)
                elif e.type == pygame.MOUSEMOTION:
                    self.lab.mouse_move(e.pos, e.buttons)
                elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                    self.lab.mouse_up(e.pos, e.button)
                elif e.type == pygame.MOUSEWHEEL:
                    self.lab.wheel(e.y)
                continue
            if e.type == pygame.KEYDOWN:
                self.key(e.key, e)
            elif e.type == pygame.MOUSEBUTTONDOWN:
                self.click(e.pos, e.button)
            elif e.type == pygame.MOUSEWHEEL:
                if self.modal in ("woerterbuch", "inventory", "trade"):
                    self.scroll = max(0, self.scroll - e.y)
                elif self.modal is None:
                    p.inv.selected = (p.inv.selected - e.y) % p.inv.BELT
                    g.sync_held()

    def key(self, k, e):
        g = self.g
        p = g.player
        m = self.modal
        if m == "card":
            if k in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_ESCAPE, pygame.K_e):
                cb = self.card.get("on_close")
                self.card = None
                self.modal = None
                if cb:
                    cb()
            return
        if m == "death":
            if k in (pygame.K_r, pygame.K_SPACE, pygame.K_RETURN):
                self.modal = None
                g.respawn()
            elif k == pygame.K_ESCAPE:
                g.app.to_menu()
            return
        if m == "pause":
            if k == pygame.K_ESCAPE or k == pygame.K_1:
                self.modal = None
            elif k == pygame.K_2:
                g.app.save_game()
                self.toast("[Gespeichert|saved].")
                self.modal = None
            elif k == pygame.K_3:
                self.modal = "help"
            elif k == pygame.K_4:
                g.app.to_menu()
            return
        if m == "dialogue":
            if k == pygame.K_ESCAPE:
                self.close_dialogue()
            elif pygame.K_1 <= k <= pygame.K_9:
                i = k - pygame.K_1
                if i < len(self.dlg_opts):
                    self.dlg_opts[i][2]()
            return
        if m == "trade":
            if k in (pygame.K_ESCAPE, pygame.K_e):
                self.modal = "dialogue"
            return
        if m == "woerterbuch" and self.quiz is not None:
            if k == pygame.K_ESCAPE:
                self.quiz = None
            elif pygame.K_1 <= k <= pygame.K_4:
                self.answer_quiz(k - pygame.K_1)
            return
        if m in ("inventory", "map", "woerterbuch", "stand", "help", "build"):
            close = {"inventory": (pygame.K_i, pygame.K_ESCAPE, pygame.K_TAB), "map": (pygame.K_m, pygame.K_ESCAPE),
                     "woerterbuch": (pygame.K_n, pygame.K_ESCAPE), "stand": (pygame.K_r, pygame.K_ESCAPE),
                     "help": (pygame.K_h, pygame.K_F1, pygame.K_ESCAPE), "build": (pygame.K_b, pygame.K_ESCAPE)}[m]
            if k in close:
                self.modal = None
                self.build_sel = None
                return
            if m == "woerterbuch" and k == pygame.K_q:
                self.start_quiz()
            if m == "build" and pygame.K_1 <= k <= pygame.K_9:
                pass
            if m == "inventory":
                bagui.bag_key(self, k)
                return
            if m != "build":
                return
        if self.order_bar:
            if k in (pygame.K_ESCAPE, pygame.K_x):
                self.order_bar = False
            else:
                self.order_key(k)
            return
        # free play hotkeys
        if k == pygame.K_ESCAPE:
            if self.build_sel is not None:
                self.build_sel = None
                self.modal = None
            else:
                self.open("pause")
        elif k == pygame.K_e:
            if g.ctrl.shaping is None:
                g.interact()
        elif k == pygame.K_i:
            self.open("inventory")
        elif k == pygame.K_b:
            self.open("build")
        elif k == pygame.K_m:
            self.open("map")
        elif k == pygame.K_n:
            self.open("woerterbuch")
        elif k == pygame.K_r:
            held = ITEMS.get(p.inv.held()) if p.inv.held() else None
            if getattr(p, "carrying", None) is None and not (held is not None and held.cat == "place"):
                self.open("stand")
        elif k in (pygame.K_h, pygame.K_F1):
            self.open("help")
        elif k == pygame.K_x:
            self.order_bar = True
        elif k == pygame.K_TAB:
            hs = p.haufen
            if hs:
                p.selected_haufen = (p.selected_haufen + 1) % (len(hs) + 1) - 0
                if p.selected_haufen >= len(hs):
                    p.selected_haufen = -1
                for i, h in enumerate(hs):
                    h.selected = (p.selected_haufen == -1 or i == p.selected_haufen)
                sel = "alle (all)" if p.selected_haufen == -1 else hs[p.selected_haufen].unit.de
                self.toast(f"[Ausgewählt|selected]: {sel}", 2)
        elif k == pygame.K_z:
            g.set_zoom(0.6 if getattr(g, "zoom", 1.0) == 1.0 else 1.0)
            self.toast("[Feldherrenblick|commander's view] " + ("an (on)" if g.zoom != 1.0 else "aus (off)"), 2)
        elif k == pygame.K_v:
            g.fire_arrows = not g.fire_arrows
            self.toast("[Brandpfeile|fire arrows] " + ("an (on)" if g.fire_arrows else "aus (off)"), 2)
        elif k == pygame.K_F5:
            g.app.save_game()
            self.toast("[Gespeichert|saved].")
        elif k == pygame.K_F9:
            g.app.load_game()
        elif k == pygame.K_q:
            held = p.inv.held()
            if held:
                p.inv.remove(held, 1)
                g.drop_item(held, 1, p.cx + p.facing * 30, p.y)
                g.sync_held()
        elif k == pygame.K_t:
            # quick toggle: equip the next armour / shield in your bag
            self.cycle_gear()
        elif pygame.K_1 <= k <= pygame.K_4:
            p.inv.selected = k - pygame.K_1
            g.sync_held()

    def cycle_gear(self):
        g = self.g
        p = g.player
        for s in p.inv.slots:
            if not s:
                continue
            d = ITEMS[s[0]]
            if d.cat == "shield" and (p.shield is None or p.shield.key != s[0]):
                p.equip(shield=s[0])
                self.toast(f"[Schild|shield]: {d.de}", 2)
                return
            if d.cat == "armor" and p.armor.key != s[0]:
                p.equip(armor=s[0])
                self.toast(f"[Rüstung|armour]: {d.de}", 2)
                return
            if d.cat == "helmet" and p.helmet != s[0]:
                p.equip(helmet=s[0])
                self.toast(f"[Helm|helmet]: {d.de}", 2)
                return

    def click(self, pos, button):
        g = self.g
        m = self.modal
        if m == "inventory":
            bagui.bag_click(self, pos, button)
        elif m == "trade":
            self.trade_click(pos, button)
        elif m == "build":
            self.build_click(pos, button)
        elif m == "dialogue":
            for i, (rect, _, cb) in enumerate(self.dlg_rects if hasattr(self, "dlg_rects") else []):
                if rect.collidepoint(pos):
                    cb()
                    return
        elif m == "map":
            self.map_click(pos)
        elif m == "pause":
            for i, r in enumerate(getattr(self, "pause_rects", [])):
                if r.collidepoint(pos):
                    self.key([pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4][i], None)
        elif m == "card":
            self.key(pygame.K_SPACE, None)
        elif m is None and self.build_sel is not None:
            self.build_click(pos, button)

    # ------------------------------------------------------------------ orders
    ORDER_KEYS = ["vorwaerts", "halt", "angriff", "zurueck", "schildwall", "igel", "keil", "locker", "wechsel",
                  "folgt", "formiert", "aufloesen", "salve"]

    def order_key(self, k):
        g = self.g
        p = g.player
        idx = {pygame.K_1: 0, pygame.K_2: 1, pygame.K_3: 2, pygame.K_4: 3, pygame.K_5: 4, pygame.K_6: 5,
               pygame.K_7: 6, pygame.K_8: 7, pygame.K_9: 8, pygame.K_0: 9, pygame.K_MINUS: 10, pygame.K_EQUALS: 11,
               pygame.K_BACKSPACE: 12}.get(k)
        if idx is None:
            return
        order = self.ORDER_KEYS[idx]
        self.order_bar = False
        if order == "formiert":
            g.form_up()
            return
        if order == "aufloesen":
            g.disband()
            return
        hs = p.haufen if p.selected_haufen == -1 else [p.haufen[p.selected_haufen]] if p.haufen else []
        if order == "normal":
            pass
        p.say(D.ORDERS[order][0], t=2.5)
        g.hear(D.ORDERS[order][0], "orders")
        if not hs and p.followers:
            for f in p.followers:
                if order in ("angriff", "vorwaerts"):
                    f.brain.target = None
            return
        for h in hs:
            if order == "folgt":
                h.leader = p
                h.order = "folgt"
            elif order == "salve":
                h.order = "halt"
                h.volley_t = min(h.volley_t, 0.3)
            elif order in ("schildwall", "igel", "keil", "locker") and h.stance == order:
                h.set_order("normal", shout=False)
            else:
                h.set_order(order)

    # ------------------------------------------------------------------ dialogue
    def open_dialogue(self, npc):
        g = self.g
        self.npc = npc
        self.modal = "dialogue"
        person = getattr(npc, "person", None)
        cat = g.greeting_category()
        if person is not None and person.rank > g.player.rank + 2:
            cat = "noble" if person.job != "ruler" else "ruler"
        line = D.pick(cat, g.npc_ctx(npc), g.rng)
        if getattr(npc, "duel", False):
            line = "Draw your [Schwert|sword]! [Kämpfe|fight]!"
        self.set_line(line)
        self.build_options()

    def set_line(self, line):
        line = lingua.get().weave(line)
        self.dlg_line = line
        self.g.hear(line, "talk")

    def close_dialogue(self):
        if self.npc is not None:
            self.g.npc_say(self.npc, "farewell")
        self.modal = None
        self.npc = None

    def build_options(self):
        g = self.g
        p = g.player
        n = self.npc
        person = getattr(n, "person", None)
        opts = []
        opts.append(("[Plaudern|chat]", "chat", self.opt_chat))
        job = person.job if person else None
        if job in SELL_LISTS:
            opts.append(("[Handeln|trade]", "trade", self.opt_trade))
        if person and job not in ("child", "ruler", "lord", "knight") and not person.noble:
            opts.append(("[Gibt es Arbeit|is there work]?", "work", self.opt_work))
        if person and (job in ("guard", "farmer", "woodcutter", "miner", "shepherd", "bandit") or person.fighter) and \
                job not in ("ruler", "lord"):
            opts.append(("[Anheuern|hire] / [Rekrutieren|recruit]", "hire", self.opt_hire))
        if person and person.fighter and not getattr(n, "duel", False):
            opts.append(("[Ich fordere dich heraus|I challenge you]!", "duel", self.opt_duel))
        if job == "mayor" or (job == "ruler" and person and person.kingdom == "luebenau"):
            opts.append(("[Bürgerrecht|citizenship] (60 Pf)", "citizen", self.opt_citizen))
        if job == "knight":
            opts.append(("[Als Knappe dienen|serve as squire]", "squire", self.opt_squire))
        if job in ("lord", "ruler"):
            if p.rank == 0:
                opts.append(("[Freiheit erkaufen|buy freedom] (100 Pf)", "free", self.opt_freedom))
            opts.append(("[Lehnseid schwören|swear fealty]", "fealty", self.opt_fealty))
            opts.append(("[Um ein Lehen bitten|ask for a fief]", "fief", self.opt_fief))
        if person and person.job in ("priest", "monk") and (g.player.injury or g.player.hp < g.player.max_hp):
            opts.append(("[Heilen lassen|be healed] (5 Pf)", "heal", self.opt_heal))
        if person and person.job in ("carter",):
            opts.append(("[Fahrt|ride] → map", "travel", lambda: self.open("map")))
        if g.story is not None:
            for label, cb in g.story.dialogue_options(n):
                opts.append((label, "story", cb))
        opts.append(("[Auf Wiedersehen|goodbye]", "bye", self.close_dialogue))
        self.dlg_opts = opts

    def opt_chat(self):
        g = self.g
        person = getattr(self.npc, "person", None)
        cats = [person.job if person else "rumor", "rumor", g.greeting_category()]
        line = D.pick(g.rng.choice(cats), g.npc_ctx(self.npc), g.rng) or D.pick("rumor", g.npc_ctx(self.npc), g.rng)
        self.set_line(line)

    def opt_heal(self):
        from ..combat import injury as INJ
        p = self.g.player
        if p.inv.money < 5:
            self.set_line("A small [Spende|donation] for the [Kloster|monastery], please.")
            return
        p.inv.money -= 5
        INJ.rest(p, 24)
        p.bandaged = True
        p.hp = p.max_hp
        self.set_line("[Gott|God] heals, I only bind the [Wunden|wounds]. Go in [Frieden|peace].")

    def opt_trade(self):
        self.modal = "trade"
        self.trade_scroll = 0

    def opt_work(self):
        g = self.g
        p = g.player
        person = self.npc.person
        si = person.settlement
        m = g.society.markets[si]
        task = getattr(person, "task", None)
        if task:
            key, n, pay = task
            if p.inv.count(key) >= n:
                p.inv.remove(key, n)
                p.inv.money += pay
                p.ehre += 2
                m.stock[key] = m.stock.get(key, 0) + n
                person.task = None
                g.sfx("coin")
                self.set_line(f"[Danke|thank you]! Here: {pay} [Pfennig|pennies]. +2 [Ehre|honour].")
                g.sync_held()
            else:
                d = ITEMS[key]
                self.set_line(f"I still need {n} [{d.de}|{d.en}]. [Bitte|please].")
            return
        # pick what the market lacks
        wants = sorted(((k, m.price(k)) for k in m.stock if k in ITEMS and ITEMS[k].cat != "money"),
                       key=lambda kv: -kv[1] / max(1, ITEMS[kv[0]].value))
        key = g.rng.choice(wants[:5])[0]
        n = g.rng.randint(3, 8)
        pay = int(m.price(key) * n * 1.3) + 5
        person.task = (key, n, pay)
        d = ITEMS[key]
        self.set_line(f"[Ja|yes]! Bring me {n} [{d.de}|{d.en}] and I'll pay {pay} [Pfennig|pennies].")

    def opt_hire(self):
        g = self.g
        p = g.player
        n = self.npc
        person = n.person
        lim = rank_of(p.rank).command
        if len(p.followers) + sum(h.count for h in p.haufen) >= lim:
            self.set_line(f"A {rank_of(p.rank).de} cannot lead more than {lim} men. ([zu viele|too many])")
            return
        on_fief = person.settlement in p.fiefs
        if person.job in ("farmer", "woodcutter", "miner", "shepherd") and not on_fief:
            self.set_line("I serve my [Herr|lord], not {you}. Only my [Lehnsherr|liege lord] can call me to arms.")
            return
        cost = 0 if on_fief else (15 if person.job != "guard" else 30)
        if person.job == "guard" and p.rank < 3:
            self.set_line("A [Wache|guard] does not follow a nobody.")
            return
        if p.inv.money < cost:
            self.set_line(D.fill(D.LINES["trade_poor"][0], g.npc_ctx(n)))
            return
        p.inv.money -= cost
        n.person.settlement = -1
        n.settlement = None
        n.faction = "player"
        n.follow_idx = len(p.followers)
        n.keep = True
        if n.weapon_key in ("fists", "sichel", "hammer", "spitzhacke"):
            n.equip(weapon=g.rng.choice(["mistgabel", "flegel", "axt"]))
        g.set_brain(n, "follow")
        p.followers.append(n)
        self.set_line("[Zu Befehl|at your command]! I follow {you}." .replace("{you}", "[Euch|you]"))
        g.emit("recruit", npc=n)
        self.modal = None

    def opt_duel(self):
        g = self.g
        n = self.npc
        n.duel = True
        n.brave = True
        g.set_brain(n, "combat", target=g.player)
        n.weapon_drawn = True
        self.set_line("So be it! [Zieh|draw]! ([Ehre|honour] to the victor)")
        self.modal = None
        g.emit("duel", npc=n)

    def opt_citizen(self):
        g = self.g
        p = g.player
        if p.rank >= 2:
            self.set_line("{you} are already a [Bürger|citizen].".replace("{you}", "[Ihr|you]"))
            return
        if p.rank == 0 and p.days_in_city < 1 and not getattr(p, "freed_by_city", False):
            self.set_line("A [Leibeigener|serf]? Live here a [Jahr und Tag|year and a day] and the city air frees "
                          "you. Until then: no.")
            return
        if p.inv.money < 60:
            self.set_line("[Bürgerrecht|citizenship] costs sixty [Pfennig|pennies]. [Kein Geld|no money]?")
            return
        p.inv.money -= 60
        self.promote(2, f"You swear the [Bürgereid|citizen's oath] of {self.npc_kingdom_name()}.")
        p.citizen_of = self.npc.person.kingdom

    def opt_squire(self):
        g = self.g
        p = g.player
        if p.rank >= 3:
            self.set_line("You have outgrown the [Knappe|squire]'s shield already.")
            return
        if p.rank < 1:
            self.set_line("A [Leibeigener|serf] cannot become a [Knappe|squire]. Win your freedom first.")
            return
        if p.ehre < 30:
            self.set_line(f"Earn more [Ehre|honour] first ({p.ehre}/30). Fight robbers, help people.")
            return
        p.liege = self.npc.person.kingdom
        p.knight_master = self.npc.name
        self.promote(3, f"You kneel before {self.npc.name}. Now you carry his shield.")

    def opt_freedom(self):
        g = self.g
        p = g.player
        if p.inv.money < 100:
            self.set_line("[Freiheit|freedom] has a price: one hundred [Pfennig|pennies].")
            return
        p.inv.money -= 100
        self.promote(1, "Your lord takes the coin and strikes your name from the manor roll. You are [frei|free]!")

    def opt_fealty(self):
        g = self.g
        p = g.player
        k = self.npc.person.kingdom
        if p.liege == k:
            self.set_line("You already serve [uns|us]. Serve well.")
            return
        if p.liege and g.society.at_war(p.liege, k):
            self.set_line("You serve our [Feind|enemy]! [Raus|get out]!")
            return
        p.liege = k
        p.lord_name = self.npc.name
        p.ehre += 3
        self.set_line(f"[Ich schwöre|I swear] [Treue|loyalty] to {BY_KEY[k]['de']}. — Then rise, my [Vasall|vassal].")
        g.emit("fealty", kingdom=k)

    def opt_fief(self):
        g = self.g
        p = g.player
        person = self.npc.person
        k = person.kingdom
        if p.liege != k:
            self.set_line("First swear the [Lehnseid|oath of fealty]. A lord grants land only to his own [Vasallen|vassals].")
            return
        nxt = p.rank + 1
        if nxt < 4:
            self.set_line("A [Lehen|fief] is for [Ritter|knights]. Become a [Knappe|squire] and prove yourself.")
            return
        if nxt > 8 or nxt > person.rank:
            self.set_line("I cannot raise you above my own station.")
            return
        r = rank_of(nxt)
        if p.ehre < r.honour_needed or p.inv.money < r.money_needed:
            self.set_line(f"For [{r.de}|{r.en}] you need {r.honour_needed} [Ehre|honour] and {r.money_needed} Pf. "
                          f"You have {p.ehre} and {p.inv.money}.")
            return
        p.inv.money -= r.money_needed
        need = {4: 1, 5: 3, 6: 5, 7: 8}.get(nxt, 1)
        own = [si for si, o in g.society.owner.items() if o == k and si not in p.fiefs and
               g.world.settlements[si]["type"] in ("village", "hamlet", "castle", "town")]
        own.sort(key=lambda si: abs(g.world.settlements[si]["x0"] * TILE - p.cx))
        while len(p.fiefs) < need and own:
            si = own.pop(0)
            p.fiefs.append(si)
            g.society.lords[si] = -1
        names = ", ".join(g.world.settlements[si]["name"] for si in p.fiefs)
        self.promote(nxt, f"[Erhebt Euch|rise], {r.de}! Your [Lehen|fief]: {names}.")

    def npc_kingdom_name(self):
        k = self.npc.person.kingdom if getattr(self.npc, "person", None) else None
        return BY_KEY[k]["de"] if k in BY_KEY else "the town"

    def promote(self, level, why):
        g = self.g
        p = g.player
        old = p.rank
        p.rank = level
        r = rank_of(level)
        p.max_hp = 100 + level * 8
        colors = BY_KEY[p.liege]["colors"] if p.liege in BY_KEY else None
        p.update_look_for_rank(colors)
        p.free = level >= 1
        self.modal = None
        self.show_card(f"{r.de}", [why, "", f"[{r.de}|{r.en}] — {r.estate}", f"Fief: {r.fief}",
                                   f"Duty: {r.duty}", f"Privilege: {r.privilege}", "", r.why],
                       subtitle=f"{rank_of(old).de} → {r.de}")
        g.sfx("bell")
        g.emit("rank", level=level)

    # ------------------------------------------------------------------ trade
    def trade_goods(self):
        person = self.npc.person
        lst = SELL_LISTS.get(person.job, [])
        return [k for k in lst if k in ITEMS]

    def market(self):
        g = self.g
        si = self.npc.person.settlement
        if si is None or si < 0 or si not in g.society.markets:
            si = min(g.society.markets.keys(), key=lambda i: abs(g.world.settlements[i]["x0"] * TILE - g.player.cx))
        return g.society.markets[si]

    def trade_click(self, pos, button):
        g = self.g
        p = g.player
        m = self.market()
        n = 5 if pygame.key.get_mods() & pygame.KMOD_SHIFT else 1
        for rect, kind, key in getattr(self, "trade_rects", []):
            if not rect.collidepoint(pos):
                continue
            if kind == "buy":
                for _ in range(n):
                    price = m.price(key, True)
                    if p.inv.money < price:
                        self.toast("[Zu teuer|too expensive]!", 2)
                        break
                    if key == "horse":
                        p.inv.money -= price
                        horse = g.spawn_horse(p.cx + 30, p.feet, wild=False)
                        horse.owner = p
                        self.toast("Your new [Pferd|horse] waits beside you. Press E to mount.")
                        break
                    if key == "boat":
                        boat = next((b for b in g.boats if getattr(b, "for_sale", False)
                                     and abs(b.cx - p.cx) < 900), None)
                        if boat is None:
                            self.toast("No [Boot|boat] at this harbour.")
                            break
                        p.inv.money -= price
                        boat.for_sale = False
                        boat.owner = p
                        boat.settlement = None
                        self.toast("The [Kogge|cog] is yours! Walk onto the dock and press E.")
                        g.emit("buy_boat")
                        break
                    if p.inv.add(key, 1) == 0:
                        p.inv.money -= price
                        m.stock[key] = max(0, m.stock.get(key, 0) - 1)
                        g.sfx("coin")
                g.sync_held()
                g.emit("trade", key=key)
            elif kind == "sell":
                for _ in range(n):
                    if p.inv.count(key) <= 0:
                        break
                    price = m.price(key, False)
                    p.inv.remove(key, 1)
                    p.inv.money += price
                    m.stock[key] = m.stock.get(key, 0) + 1
                    g.sfx("coin")
                g.sync_held()
                g.emit("trade", key=key)
            return

    # ------------------------------------------------------------------ inventory & crafting
    def inv_click(self, pos, button):
        g = self.g
        p = g.player
        for rect, kind, val in getattr(self, "inv_rects", []):
            if not rect.collidepoint(pos):
                continue
            if kind == "slot":
                held = getattr(self, "drag", None)
                if held is None:
                    if p.inv.slots[val] is not None:
                        d = ITEMS[p.inv.slots[val][0]]
                        if button == 3:
                            if d.cat == "shield":
                                p.equip(shield=d.key)
                            elif d.cat == "armor":
                                p.equip(armor=d.key)
                            elif d.cat == "helmet":
                                p.equip(helmet=d.key)
                            elif d.cat == "food":
                                g.eat(p, d.key)
                            return
                        self.drag = val
                else:
                    p.inv.swap(held, val)
                    self.drag = None
                    g.sync_held()
            elif kind == "recipe":
                r = val
                st = CR.stations_near(g.world, int(p.cx // TILE), int(p.cy // TILE))
                if (r.station is None or r.station in st) and p.inv.take(r.needs):
                    p.inv.add(r.out, r.n)
                    p.stats["crafted"] += 1
                    g.sync_held()
                    g.sfx("place")
                    d = ITEMS[r.out]
                    self.toast(f"[Hergestellt|crafted]: {r.n}× [{d.de}|{d.en}]", 2)
                    g.emit("craft", key=r.out)
            elif kind == "unequip":
                if val == "shield":
                    p.equip(shield="")
                elif val == "armor":
                    p.equip(armor="kleidung")
                elif val == "helmet":
                    p.equip(helmet="")
            return

    # ------------------------------------------------------------------ building
    def build_click(self, pos, button):
        g = self.g
        p = g.player
        if self.modal == "build":
            for rect, bp in getattr(self, "build_rects", []):
                if rect.collidepoint(pos):
                    if bp.rank > p.rank:
                        self.toast(f"Needs rank [{rank_of(bp.rank).de}|{rank_of(bp.rank).en}].", 3)
                        return
                    self.build_sel = bp
                    self.modal = None
                    self.toast("Place with left click, cancel with right click / Esc.", 3)
                    return
            return
        if button == 3:
            self.build_sel = None
            return
        bp = self.build_sel
        tx, g_row = self.ghost_pos()
        if not p.inv.has(bp.cost):
            missing = ", ".join(f"{n - p.inv.count(k)}× {ITEMS[k].de}" for k, n in bp.cost.items()
                                if p.inv.count(k) < n)
            self.toast(f"[Es fehlt|missing]: {missing}", 3)
            return
        s = g.world.settlement_at(tx, margin=2)
        if s is not None and g.world.settlements.index(s) not in p.fiefs and bp.key not in ("field",):
            self.toast("Not on another lord's land! Build on your own [Lehen|fief] or in the wild.", 3)
            return
        p.inv.take(bp.cost)
        if bp.engine:
            e = g.spawn_engine(bp.engine, (tx + bp.width / 2) * TILE, "player", p.facing,
                               BY_KEY[p.liege]["colors"] if p.liege in BY_KEY else None)
            e.active = False
            self.toast(f"{bp.de} ({bp.en}) built. Walk up to it and press E.", 4)
            g.sync_held()
            self.build_sel = None
            return
        n = g.queue_blueprint(bp, tx, g_row)
        self.toast(f"[Baustelle|construction site]: {bp.de} ({n} tiles)", 3)
        g.sync_held()
        self.build_sel = None

    def ghost_pos(self):
        g = self.g
        mx, my = pygame.mouse.get_pos()
        z = getattr(g, "zoom", 1.0)
        mx, my = mx / z, my / z
        ox, oy = g.camera.offset()
        tx = int((mx + ox) // TILE) - self.build_sel.width // 2
        ty = int((my + oy) // TILE)
        row = g.world.ground_at(tx + self.build_sel.width // 2, max(0, ty - 6))
        return tx, row

    # ------------------------------------------------------------------ map
    def build_map(self):
        w = self.g.world
        W = SCREEN_W - 80
        H = 220
        img = pygame.Surface((W, H))
        img.fill((20, 22, 30))
        xs = np.linspace(0, w.w - 1, W).astype(int)
        top = 20
        scale = (H - 40) / 160
        biome_col = {"abyss": (20, 10, 30), "edge": (110, 100, 90), "plains": (110, 150, 70), "forest": (50, 100, 50),
                     "moor": (80, 90, 60), "hills": (120, 140, 80), "mountains": (130, 126, 120),
                     "vineyard": (130, 120, 70), "coast": (190, 180, 120), "ocean": (40, 80, 130),
                     "islet": (190, 180, 120), "snow": (220, 226, 236), "ashland": (100, 90, 86),
                     "volcanic": (70, 50, 50), "lavasea": (220, 90, 30)}
        for i, x in enumerate(xs):
            b = w.biome_at(int(x))
            s = int(w.surface[x])
            y = top + (s - 30) * scale
            pygame.draw.line(img, biome_col.get(b, (100, 100, 100)), (i, y), (i, H))
            if s > SEA_LEVEL and b in ("ocean", "lavasea", "coast"):
                pygame.draw.line(img, (40, 90, 150) if b != "lavasea" else (230, 100, 30),
                                 (i, top + (SEA_LEVEL - 30) * scale), (i, y))
        self.map_img = img
        self.map_scale = W / w.w

    def map_click(self, pos):
        g = self.g
        p = g.player
        for rect, si in getattr(self, "map_rects", []):
            if rect.collidepoint(pos):
                s = g.world.settlements[si]
                here = g.world.settlement_at(int(p.cx // TILE), margin=30)
                if here is None or here["type"] not in ("town", "city", "capital", "port", "village"):
                    self.toast("A [Fuhrmann|carter] only leaves from a settlement.", 3)
                    return
                ocean = [r for r in g.world.regions if r[2] == "ocean"]
                a, b = sorted((p.cx / TILE, (s["x0"] + s["x1"]) / 2))
                if any(a < r0 < b for r0, r1, _ in ocean):
                    self.toast("The [Fuhrmann|carter] can't cross the sea. Take a [Boot|boat].", 3)
                    return
                dist = abs((s["x0"] + s["x1"]) / 2 - p.cx / TILE)
                cost = max(3, int(dist / 400))
                if p.inv.money < cost:
                    self.toast(f"The ride costs {cost} Pf.", 3)
                    return
                p.inv.money -= cost
                tx = (s["x0"] + s["x1"]) // 2
                gy = g.world.ground_at(tx, max(0, s["g"] - 20))
                p.x, p.y = tx * TILE, gy * TILE - p.h - 1
                for f in p.followers:
                    f.x, f.y = p.x - 30, p.y
                if p.mount is not None:
                    p.mount.x, p.mount.y = p.x - 10, p.y
                g.env.time += dist * TILE / 60.0
                g.camera.snap(p.cx, p.cy)
                self.modal = None
                self.fade(f"[Mit dem Wagen|by cart] to {s['name']}… ({cost} Pf)")
                return

    # ------------------------------------------------------------------ quiz
    def start_quiz(self):
        words = list(self.g.player.dict.words.items())
        if len(words) < 4:
            self.toast("Learn at least 4 words first.", 2)
            return
        de, (en, _, _) = random.choice(words)
        wrong = random.sample([w for w in words if w[0] != de], 3)
        opts = [en] + [w[1][0] for w in wrong]
        random.shuffle(opts)
        self.quiz = {"de": de, "en": en, "opts": opts, "result": None, "score": getattr(self, "quiz_score", 0)}

    def answer_quiz(self, i):
        q = self.quiz
        if q["result"] is not None:
            self.start_quiz()
            return
        ok = q["opts"][i] == q["en"]
        q["result"] = ok
        if ok:
            for _ in range(3):
                lingua.get().heard(q["de"], q["en"])
        self.quiz_score = getattr(self, "quiz_score", 0) + (1 if ok else 0)
        if ok and self.quiz_score % 5 == 0:
            self.g.player.ehre += 1
            self.toast("[Gelehrt|learned]! +1 [Ehre|honour] for your studies.", 3)

    # ================================================================== drawing
    def draw_world_overlays(self, surf, ox, oy):
        g = self.g
        p = g.player
        # speech bubbles
        for h in g.humanoids:
            if h.bubble and abs(h.cx - p.cx) < 700:
                self.bubble(surf, h, ox, oy)
        if p.bubble:
            self.bubble(surf, p, ox, oy)
        if self.modal is None and self.build_sel is None and g.ctrl.shaping is None:
            mx, my = pygame.mouse.get_pos()
            z = getattr(g, "zoom", 1.0)
            wx, wy = mx / z + ox, my / z + oy
            if math.hypot(wx - p.cx, wy - p.cy) < 92:
                label = self.hover_label(wx, wy)
                if label:
                    text(surf, label, (wx - ox, wy - oy - 22), 11, center=True, color=(230, 220, 190))
        # build ghost
        if self.build_sel is not None:
            bp = self.build_sel
            tx, row = self.ghost_pos()
            ok = p.inv.has(bp.cost)
            col = (120, 230, 120, 70) if ok else (230, 100, 90, 70)
            gh = pygame.Surface((bp.width * TILE, 12 * TILE), pygame.SRCALPHA)
            gh.fill(col)
            surf.blit(gh, (tx * TILE - ox, row * TILE - oy - 12 * TILE))
            pygame.draw.rect(surf, col[:3], (tx * TILE - ox, row * TILE - oy - 12 * TILE, bp.width * TILE, 12 * TILE), 1)
            cost = "  ".join(f"{ITEMS[k].de} {p.inv.count(k)}/{n}" for k, n in bp.cost.items())
            text(surf, f"{bp.de} ({bp.en}) — {cost}", (tx * TILE - ox, row * TILE - oy - 12 * TILE - 22), 13)

    def hover_label(self, wx, wy):
        from ..poly.prefab import piece_at
        from ..poly.materials import MATS
        from ..poly.objects import objects_near
        w = self.g.world
        for t in w.near("tree_chunks", wx - 60, wx + 60):
            if t.state == "stand" and abs(t.x - wx) < t.tw / 2 + 10 and t.y - t.h * 0.6 < wy < t.y + 4:
                de = {"oak": "Eiche", "beech": "Buche", "birch": "Birke", "pine": "Kiefer", "fir": "Tanne",
                      "lime": "Linde", "willow": "Weide", "dead": "toter Baum"}.get(t.kind, "Baum")
                return f"{de} — fell it with an Axt ({int(100 * t.hp / max(1, t.max_hp))}%)"
        for o in objects_near(w, wx, wy, 6):
            if o.shape is not None and o.shape.point_query((wx, wy)).distance < 4:
                if o.kind == "log":
                    return "Stamm (log) — E carry · Axt: cut · C shape"
                nm = ITEMS[o.item].de if o.item in ITEMS else (o.name or MATS[o.mat].de)
                if o.kind == "crafted" and o.shape_key:
                    return f"{nm} — Güte {int(o.quality * 100)}%"
                return nm
        for ore in w.ores:
            if ore["left"] > 0 and abs(ore["x"] - wx) < 14 and abs(ore["y"] - wy) < 14:
                return {"coal": "Kohle", "iron": "Eisenerz", "silver": "Silbererz", "gold": "Golderz",
                        "salt": "Salz", "glutstein": "Glutstein", "stone": "Stein"}[ore["kind"]] + " — Spitzhacke"
        pc = piece_at(w, wx, wy)
        if pc is not None and pc.solid:
            m = MATS[pc.mat]
            return f"{m.de} ({m.en}) {int(100 * pc.hp / max(1, pc.max_hp))}%"
        return None

    def bubble(self, surf, h, ox, oy):
        line, t, _ = h.bubble
        segs, gl = D.parse(line)
        plain = "".join(s for s, _ in segs)
        f = self.small
        width = min(320, f.size(plain)[0] + 20)
        x = h.cx - ox
        y = h.y - oy - 26
        tmp = pygame.Surface((width + 40, 120), pygame.SRCALPHA)
        hgt = bilingual(tmp, line, (6, 4), 13, width - 4, gloss=True)
        box = pygame.Rect(x - width / 2 - 6, y - hgt - 6, width + 12, hgt + 10)
        a = min(1.0, t * 2)
        bg = pygame.Surface(box.size, pygame.SRCALPHA)
        bg.fill((24, 20, 18, int(200 * a)))
        surf.blit(bg, box.topleft)
        pygame.draw.rect(surf, (180, 150, 90), box, 1, border_radius=4)
        pygame.draw.polygon(surf, (24, 20, 18), [(x - 5, box.bottom), (x + 5, box.bottom), (x, box.bottom + 6)])
        tmp.set_alpha(int(255 * a))
        surf.blit(tmp, (box.x + 2, box.y + 2))

    def draw(self, surf):
        g = self.g
        p = g.player
        self.draw_hud(surf)
        if self.order_bar:
            self.draw_orders(surf)
        m = self.modal
        if m == "dialogue":
            self.draw_dialogue(surf)
        elif m == "trade":
            self.draw_trade(surf)
        elif m == "inventory":
            bagui.draw_bag(self, surf)
        elif m == "lab" and getattr(self, "lab", None) is not None:
            self.lab.draw(surf)
        elif m == "build":
            self.draw_build(surf)
        elif m == "map":
            self.draw_map(surf)
        elif m == "woerterbuch":
            self.draw_woerterbuch(surf)
        elif m == "stand":
            self.draw_stand(surf)
        elif m == "help":
            self.draw_help(surf)
        elif m == "pause":
            self.draw_pause(surf)
        elif m == "death":
            self.draw_death(surf)
        elif m == "card":
            self.draw_card(surf)
        if self.fade_t > 0:
            a = min(1.0, self.fade_t / 0.6) if self.fade_t < 0.6 else min(1.0, (2.2 - self.fade_t) / 0.4)
            s = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            s.fill((0, 0, 0, int(255 * a)))
            surf.blit(s, (0, 0))
            if a > 0.5:
                bilingual(surf, self.fade_text, (SCREEN_W // 2, SCREEN_H // 2 - 10), 22, 900, center=True)

    # ------------------------------------------------------------------ HUD
    def draw_hud(self, surf):
        g = self.g
        p = g.player
        # vitals
        panel(surf, (10, 10, 250, 92), 170)
        bar(surf, 20, 20, 150, 12, p.hp / p.max_hp, (190, 50, 44))
        ltext(surf, f"Life {int(p.hp)}", (176, 16), 12)
        bar(surf, 20, 38, 150, 8, p.stamina / p.max_stamina, (220, 190, 70))
        ltext(surf, "Stamina", (176, 33), 11, (200, 200, 190))
        bar(surf, 20, 52, 150, 8, p.hunger / 100, (150, 110, 60))
        ltext(surf, "Hunger", (176, 47), 11, (200, 200, 190))
        if p.head_under or p.breath < 12:
            bar(surf, 20, 66, 150, 6, p.breath / 12, (120, 180, 240))
            ltext(surf, "Breath", (176, 61), 11)
        self.draw_body_doll(surf, 266, 10, p)
        r = rank_of(p.rank)
        text(surf, f"{r.de} ({r.en})", (20, 78), 13, GERMAN_COLOR)
        text(surf, f"{p.inv.money} Pf · Ehre {p.ehre}", (250, 78), 12, right=True)
        # top right: time, weather, wind, place
        env = g.env
        se = env.season_name()
        k, wde, wen = env.current()
        panel(surf, (SCREEN_W - 290, 10, 280, 74), 170)
        ltext(surf, f"Day {env.day + 1} · {env.clock_text()} · {se[1]}", (SCREEN_W - 280, 16), 13)
        ltext(surf, wen, (SCREEN_W - 280, 34), 13, (200, 210, 230))
        sp = abs(env.wind)
        wt = ("calm" if sp < 0.12 else "breeze" if sp < 0.45 else "wind" if sp < 0.8 else "gale") + \
            (" → east" if env.wind > 0 else " ← west")
        ltext(surf, wt, (SCREEN_W - 280, 52), 12, (190, 200, 210))
        tx = int(p.cx // TILE)
        s = g.world.settlement_at(tx, margin=20)
        kk = g.world.kingdom_at(tx)
        b = g.world.biome_at(tx)
        loc = s["name"] if s else BIOME_NAMES.get(b, (b, b))[0]
        realm = BY_KEY[g.society.owner.get(g.world.settlements.index(s), kk) if s else kk]["de"] if (s or kk) else \
            BIOME_NAMES.get(b, (b, b))[0]
        if loc != self.last_loc:
            self.last_loc = loc
            self.loc_t = 4.0
        if self.loc_t > 0:
            self.loc_t -= 1 / 60
            a = min(1.0, self.loc_t)
            img = self.big.render(loc, True, (240, 220, 170))
            img.set_alpha(int(255 * a))
            surf.blit(img, (SCREEN_W // 2 - img.get_width() // 2, 86))
            sub = self.med.render(realm, True, (200, 190, 160))
            sub.set_alpha(int(255 * a))
            surf.blit(sub, (SCREEN_W // 2 - sub.get_width() // 2, 122))
        text(surf, f"{loc} — {realm}", (SCREEN_W - 280, 68), 11, (170, 170, 160))
        # hotbar
        nb = p.inv.BELT
        hb_w = nb * 50 + 120
        x0 = SCREEN_W // 2 - hb_w // 2
        y0 = SCREEN_H - 56
        # the belt: four things within reach
        pygame.draw.rect(surf, (92, 64, 40), (x0 - 8, y0 + 16, nb * 50 + 14, 10), border_radius=4)
        for i in range(nb):
            rr = pygame.Rect(x0 + i * 50, y0, 44, 44)
            sel = i == p.inv.selected
            panel(surf, rr, 200 if sel else 150, border=GOLD if sel else (90, 80, 60))
            k_ = p.inv.belt[i]
            if k_ and p.inv.count(k_):
                item_icon(surf, k_, rr)
                n_ = p.inv.count(k_)
                if n_ > 1:
                    text(surf, str(n_), (rr.right - 4, rr.bottom - 15), 11, right=True)
            text(surf, str(i + 1), (rr.x + 3, rr.y + 1), 10, (160, 150, 130))
        # the bag
        br = pygame.Rect(x0 + nb * 50 + 16, y0 - 4, 96, 50)
        pygame.draw.ellipse(surf, (110, 84, 56), br.inflate(-30, -6))
        pygame.draw.polygon(surf, (92, 70, 46), [(br.x + 26, br.y + 8), (br.right - 26, br.y + 8),
                                                 (br.centerx, br.y - 2)])
        wfrac = p.inv.weight() / p.inv.capacity
        text(surf, f"{p.inv.weight():.0f}/{p.inv.capacity:.0f}kg", (br.centerx, br.y + 18), 10,
             (240, 220, 180) if wfrac < 0.9 else (240, 140, 110), center=True)
        text(surf, "I", (br.centerx, br.bottom - 14), 10, (180, 170, 150), center=True)
        if getattr(p, "carrying", None) is not None:
            o = p.carrying
            nm = ITEMS[o.item].de if o.item in ITEMS else "Stamm"
            ltext(surf, f"carrying: {nm} — click to set down (Shift: fix in place), R rotate, G throw",
                  (SCREEN_W // 2, y0 - 40), 12, (236, 226, 200), center=True)
        held = p.inv.held()
        if held:
            d = ITEMS[held]
            extra = ""
            if d.weapon and WEAPONS[d.weapon].kind in ("bow",):
                extra = f"  · {p.inv.count('arrow')} Pfeile" + (" (Brand)" if g.fire_arrows else "")
            ltext(surf, f"{d.en}{extra}", (SCREEN_W // 2, y0 - 20), 14, (236, 226, 200), center=True)
        # formations
        if p.haufen or p.followers:
            y = 110
            panel(surf, (10, y, 250, 20 + 18 * (len(p.haufen) + (1 if p.followers else 0))), 150)
            yy = y + 8
            if p.followers:
                text(surf, f"Gefolge (retinue): {len(p.followers)}", (20, yy), 12)
                yy += 18
            for i, h in enumerate(p.haufen):
                sel = p.selected_haufen in (-1, i)
                od = D.plain(D.ORDERS[h.order][0]).rstrip("!") if h.order in D.ORDERS else \
                    {"flucht": "Flucht"}.get(h.order, h.order)
                text(surf, f"{'▸' if sel else ' '} {h.unit.de}: {h.count} · {od} · Moral {int(max(0, h.morale))}",
                     (20, yy), 12, (240, 220, 150) if sel else (200, 200, 190))
                yy += 18
            text(surf, "X = Befehle (orders) · Tab = select", (20, yy + 2), 10, (150, 150, 140))
        # messages
        y = SCREEN_H - 120
        for line, t in reversed(self.g.messages[-4:]):
            tmp = pygame.Surface((560, 60), pygame.SRCALPHA)
            hgt = bilingual(tmp, line, (0, 0), 13, 540, gloss=False)
            tmp.set_alpha(int(255 * min(1.0, t)))
            surf.blit(tmp, (14, y - hgt))
            y -= hgt + 2
        # toasts
        y = 150
        for line, t in self.toasts:
            tmp = pygame.Surface((900, 70), pygame.SRCALPHA)
            hgt = bilingual(tmp, line, (450, 6), 16, 860, center=True)
            box = pygame.Rect(SCREEN_W // 2 - 300, y, 600, hgt + 10)
            panel(surf, box, int(180 * min(1.0, t)), border=None)
            tmp.set_alpha(int(255 * min(1.0, t)))
            surf.blit(tmp, (SCREEN_W // 2 - 450, y))
            y += hgt + 14
        # story objective
        if g.story is not None:
            g.story.draw_objective(surf)
        if g.battle is not None:
            g.battle.draw_hud(surf)
        # tiny controls hint
        ltext(surf, "H = help", (SCREEN_W - 12, SCREEN_H - 18), 11, (150, 150, 140), right=True)

    def draw_body_doll(self, surf, x, y, h):
        """Little body diagram: each part coloured by its wound level, armour hardness as an outline."""
        from ..combat import injury as INJ
        panel(surf, (x, y, 44, 92), 170)
        cols = [(110, 170, 90), (220, 190, 60), (230, 120, 50), (200, 40, 40)]
        inj = h.injury
        cx = x + 22

        def c(part):
            return cols[inj.get(part, 0)]

        def edge(part):
            hd = INJ.hardness(h, part)
            return (210, 214, 224) if hd >= 5 else (170, 150, 110) if hd > 0 else (40, 34, 30)
        pygame.draw.circle(surf, c("head"), (cx, y + 14), 6)
        pygame.draw.circle(surf, edge("head"), (cx, y + 14), 6, 1)
        r = pygame.Rect(cx - 7, y + 22, 14, 26)
        pygame.draw.rect(surf, c("torso"), r)
        pygame.draw.rect(surf, edge("torso"), r, 1)
        for part, ax in (("arm_s", cx - 13), ("arm_w", cx + 9)):
            ra = pygame.Rect(ax, y + 23, 4, 24)
            pygame.draw.rect(surf, c(part), ra)
            pygame.draw.rect(surf, edge(part), ra, 1)
        for lx in (cx - 6, cx + 1):
            rl = pygame.Rect(lx, y + 50, 5, 28)
            pygame.draw.rect(surf, c("legs"), rl)
            pygame.draw.rect(surf, edge("legs"), rl, 1)
        if inj and not h.bandaged and any(v >= 1 for v in inj.values()):
            if (pygame.time.get_ticks() // 400) % 2 == 0:
                pygame.draw.polygon(surf, (200, 30, 30), [(x + 36, y + 80), (x + 39, y + 73), (x + 42, y + 80),
                                                          (x + 39, y + 84)])
        elif h.bandaged and inj:
            text(surf, "+", (x + 36, y + 72), 14, (236, 230, 214))

    def draw_orders(self, surf):
        g = self.g
        p = g.player
        keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "=", "⌫"]
        w = 300
        h = 26 + len(self.ORDER_KEYS) * 22
        r = panel(surf, (SCREEN_W - w - 14, 100, w, h), 220)
        text(surf, "Befehle (orders)", (r.x + 10, r.y + 6), 15, GOLD)
        for i, o in enumerate(self.ORDER_KEYS):
            de, en = D.ORDERS[o]
            y = r.y + 28 + i * 22
            text(surf, keys[i], (r.x + 12, y), 13, (200, 200, 190))
            bilingual(surf, de, (r.x + 36, y), 13, 140, gloss=False)
            text(surf, en, (r.x + 150, y + 1), 11, (170, 180, 190))

    def draw_dialogue(self, surf):
        g = self.g
        n = self.npc
        if n is None:
            self.modal = None
            return
        person = getattr(n, "person", None)
        r = panel(surf, (SCREEN_W // 2 - 420, SCREEN_H - 330, 840, 300), 235)
        # portrait
        pr = pygame.Rect(r.x + 16, r.y + 16, 120, 150)
        panel(surf, pr, 255, color=(50, 44, 40))
        port = pygame.Surface((60, 75), pygame.SRCALPHA)
        old = n.facing
        n.facing = 1
        draw_humanoid(port, n, 30, 70)
        n.facing = old
        surf.blit(pygame.transform.scale(port, (120, 150)), pr.topleft)
        job = person.job if person else "?"
        jde, jen = JOB_DE.get(job, (job, job))
        title = (person.title + " ") if person and person.title and person.title not in n.name else ""
        text(surf, f"{title}{n.name}", (r.x + 150, r.y + 14), 20, GOLD, bold=True)
        rk = rank_of(person.rank if person else 0)
        sub = f"{jde} ({jen}) · {rk.de} ({rk.en})"
        if person and person.kingdom in BY_KEY:
            sub += f" · {BY_KEY[person.kingdom]['de']}"
        text(surf, sub, (r.x + 150, r.y + 40), 13, (200, 190, 170))
        if self.dlg_line:
            bilingual(surf, self.dlg_line, (r.x + 150, r.y + 68), 18, 660)
        self.dlg_rects = []
        y = r.y + 170
        col_w = 400
        for i, (label, kind, cb) in enumerate(self.dlg_opts):
            cx = r.x + 20 + (i % 2) * col_w
            cy = y + (i // 2) * 26
            rect = pygame.Rect(cx, cy, col_w - 20, 24)
            hov = rect.collidepoint(pygame.mouse.get_pos())
            if hov:
                pygame.draw.rect(surf, (70, 60, 40), rect, border_radius=3)
            text(surf, f"{i + 1}.", (cx + 4, cy + 3), 14, GOLD)
            bilingual(surf, label, (cx + 26, cy + 3), 14, col_w - 50, gloss=False)
            self.dlg_rects.append((rect, kind, cb))

    def draw_trade(self, surf):
        g = self.g
        p = g.player
        m = self.market()
        r = panel(surf, (SCREEN_W // 2 - 460, 60, 920, SCREEN_H - 120), 235)
        ltext(surf, f"Trade with {self.npc.name} — {p.inv.money} pennies", (r.x + 16, r.y + 10), 20, GOLD)
        text(surf, "Click: buy/sell one · Shift+Click: five · Esc: back. Prices follow supply & demand.",
             (r.x + 16, r.y + 38), 12, (190, 190, 180))
        self.trade_rects = []
        goods = self.trade_goods()
        text(surf, "[Kaufen] Buy", (r.x + 16, r.y + 62), 15, GERMAN_COLOR)
        for i, key in enumerate(goods[:22]):
            d = ITEMS[key]
            y = r.y + 86 + i * 24
            rect = pygame.Rect(r.x + 14, y, 430, 22)
            if rect.collidepoint(pygame.mouse.get_pos()):
                pygame.draw.rect(surf, (70, 60, 40), rect, border_radius=3)
            item_icon(surf, key, (rect.x, rect.y - 1, 24, 24))
            stock = m.stock.get(key, "–")
            text(surf, f"{d.de} ({d.en})", (rect.x + 30, y + 3), 13)
            text(surf, f"{m.price(key, True)} Pf", (rect.right - 70, y + 3), 13, (230, 210, 140))
            text(surf, f"[{stock}]", (rect.right - 4, y + 3), 11, (150, 150, 140), right=True)
            self.trade_rects.append((rect, "buy", key))
        text(surf, "[Verkaufen] Sell", (r.x + 470, r.y + 62), 15, GERMAN_COLOR)
        seen = []
        for s_ in p.inv.slots:
            if s_ and s_[0] not in seen:
                seen.append(s_[0])
        for i, key in enumerate(seen[:22]):
            d = ITEMS[key]
            y = r.y + 86 + i * 24
            rect = pygame.Rect(r.x + 466, y, 430, 22)
            if rect.collidepoint(pygame.mouse.get_pos()):
                pygame.draw.rect(surf, (70, 60, 40), rect, border_radius=3)
            item_icon(surf, key, (rect.x, rect.y - 1, 24, 24))
            text(surf, f"{d.de} ×{p.inv.count(key)}", (rect.x + 30, y + 3), 13)
            text(surf, f"{m.price(key, False)} Pf", (rect.right - 10, y + 3), 13, (230, 210, 140), right=True)
            self.trade_rects.append((rect, "sell", key))

    def draw_inventory(self, surf):
        g = self.g
        p = g.player
        r = panel(surf, (40, 40, SCREEN_W - 80, SCREEN_H - 80), 235)
        ltext(surf, "Inventory & crafting", (r.x + 16, r.y + 10), 20, GOLD)
        text(surf, "Click to pick up / swap · Right-click to equip/eat · I or Esc to close", (r.x + 16, r.y + 38), 12,
             (190, 190, 180))
        self.inv_rects = []
        mp = pygame.mouse.get_pos()
        tip = None
        for i in range(40):
            col, row = i % 10, i // 10
            rect = pygame.Rect(r.x + 16 + col * 48, r.y + 64 + row * 48, 44, 44)
            sel = i == p.inv.selected or getattr(self, "drag", None) == i
            panel(surf, rect, 200, border=GOLD if sel else (90, 80, 60))
            s_ = p.inv.slots[i]
            if s_:
                item_icon(surf, s_[0], rect)
                if s_[1] > 1:
                    text(surf, str(s_[1]), (rect.right - 3, rect.bottom - 15), 11, right=True)
                if rect.collidepoint(mp):
                    tip = s_[0]
            self.inv_rects.append((rect, "slot", i))
        # equipment
        ex = r.x + 16
        ey = r.y + 64 + 4 * 48 + 14
        text(surf, "Ausrüstung (equipment):", (ex, ey), 14, GERMAN_COLOR)
        eq = [("Waffe", p.weapon_def.de, None),
              ("Schild", p.shield.de if p.shield else "—", "shield"),
              ("Rüstung", p.armor.de, "armor"),
              ("Helm", HELMET_NAMES[p.helmet][0] if p.helmet else "—", "helmet")]
        for i, (lab, val, kind) in enumerate(eq):
            rect = pygame.Rect(ex, ey + 22 + i * 22, 300, 20)
            text(surf, f"{lab}: {val}", (rect.x, rect.y), 13)
            if kind:
                self.inv_rects.append((rect, "unequip", kind))
        wd = p.weapon_def
        text(surf, f"{wd.de}: {wd.dmg:.0f} dmg · {wd.dtype} · reach {wd.reach:.0f} — {wd.note}", (ex, ey + 116), 12,
             (190, 190, 180))
        # stats
        text(surf, f"Wörter gelernt (words learned): {len(p.dict.words)} · Kills {p.stats['kills']} · Gebaut "
                   f"{p.stats['built']}", (ex, ey + 140), 12, (190, 190, 180))
        # recipes
        st = CR.stations_near(g.world, int(p.cx // TILE), int(p.cy // TILE))
        rx = r.x + 530
        text(surf, "Handwerk (crafting) — near: " + (", ".join(st) if st else "nothing (hands only)"),
             (rx, r.y + 64), 14, GERMAN_COLOR)
        rows = CR.available(p.inv, st)
        rows.sort(key=lambda t: (not t[1], not t[2]))
        start = self.scroll
        for i, (rec, can, station_ok) in enumerate(rows[start:start + 24]):
            y = r.y + 88 + i * 22
            rect = pygame.Rect(rx, y, 680, 20)
            d = ITEMS[rec.out]
            col = (230, 230, 220) if can else (140, 140, 130) if station_ok else (100, 90, 80)
            if rect.collidepoint(mp) and can:
                pygame.draw.rect(surf, (70, 60, 40), rect, border_radius=3)
            needs = ", ".join(f"{n} {ITEMS[k].de}" for k, n in rec.needs.items())
            stn = f" @{rec.station}" if rec.station else ""
            text(surf, f"{rec.n}× {d.de} ({d.en}) ← {needs}{stn}", (rect.x + 4, y + 2), 12, col, shadow=False)
            self.inv_rects.append((rect, "recipe", rec))
            if rect.collidepoint(mp):
                tip = rec.out
        if tip:
            d = ITEMS[tip]
            extra = ""
            if d.weapon:
                extra = " — " + WEAPONS[d.weapon].note
            mx, my = mp
            tw = min(520, self.small.size(f"{d.de} ({d.en}){extra}")[0] + 20)
            panel(surf, (mx + 14, my + 10, tw, 26), 240)
            text(surf, f"{d.de} ({d.en}){extra}", (mx + 22, my + 14), 13)

    def draw_build(self, surf):
        g = self.g
        p = g.player
        r = panel(surf, (SCREEN_W // 2 - 420, 70, 840, SCREEN_H - 140), 235)
        ltext(surf, "Blueprints", (r.x + 16, r.y + 10), 20, GOLD)
        text(surf, "Pick one, then place it on the ground. Builders raise it tile by tile. Single blocks: hold "
                   "them in the hotbar and click.", (r.x + 16, r.y + 38), 12, (190, 190, 180))
        self.build_rects = []
        mp = pygame.mouse.get_pos()
        for i, bp in enumerate(BLUEPRINTS):
            y = r.y + 60 + i * 29
            rect = pygame.Rect(r.x + 14, y, r.w - 28, 28)
            ok = p.inv.has(bp.cost)
            allowed = bp.rank <= p.rank
            if rect.collidepoint(mp):
                pygame.draw.rect(surf, (70, 60, 40), rect, border_radius=3)
            col = (230, 230, 220) if ok and allowed else (150, 140, 130)
            text(surf, f"{bp.de} ({bp.en})", (rect.x + 6, y + 2), 15, GERMAN_COLOR if allowed else (130, 120, 100))
            cost = "  ".join(f"{ITEMS[k].de} {p.inv.count(k)}/{n}" for k, n in bp.cost.items())
            text(surf, cost, (rect.x + 260, y + 3), 12, col)
            text(surf, bp.note + ("" if allowed else f"  [needs {rank_of(bp.rank).de}]"), (rect.x + 260, y + 15), 11,
                 (160, 160, 150))
            self.build_rects.append((rect, bp))

    def draw_map(self, surf):
        g = self.g
        p = g.player
        w = g.world
        if self.map_img is None:
            self.build_map()
        r = panel(surf, (20, 30, SCREEN_W - 40, SCREEN_H - 60), 240)
        ltext(surf, "Map of the world", (r.x + 16, r.y + 10), 22, GOLD)
        text(surf, "From the Abyss in the west to the Fire Sea in the east — about an hour's ride. Click a "
                   "settlement to travel by cart.", (r.x + 16, r.y + 40), 12, (190, 190, 180))
        mx0, my0 = r.x + 20, r.y + 120
        surf.blit(self.map_img, (mx0, my0))
        sc = self.map_scale
        # kingdoms bands
        for kd in KINGDOMS:
            a, b = int(kd["span"][0] * w.w * sc), int(kd["span"][1] * w.w * sc)
            pygame.draw.rect(surf, kd["colors"][0], (mx0 + a, my0 - 30, b - a, 10))
            pygame.draw.line(surf, (200, 200, 200), (mx0 + a, my0 - 30), (mx0 + a, my0 + 220), 1)
            name = kd["de"].split()[-1]
            text(surf, name, (mx0 + (a + b) // 2, my0 - 52), 12, (230, 220, 190), center=True)
            text(surf, kd["realm"], (mx0 + (a + b) // 2, my0 - 16), 10, (170, 170, 160), center=True)
        text(surf, "Abgrund", (mx0 + 4, my0 + 200), 11, (200, 150, 230))
        text(surf, "Glutmeer", (mx0 + self.map_img.get_width() - 4, my0 + 200), 11, (255, 140, 60), right=True)
        oc = [rr for rr in w.regions if rr[2] == "ocean"]
        if oc:
            text(surf, "Das Graue Meer", (mx0 + int(oc[0][0] * sc) + 30, my0 + 120), 12, (180, 210, 240))
        self.map_rects = []
        mp = pygame.mouse.get_pos()
        for si, s in enumerate(w.settlements):
            x = mx0 + int((s["x0"] + s["x1"]) / 2 * sc)
            y = my0 + 20 + int((s["g"] - 30) * (180 / 160)) - 6
            owner = g.society.owner.get(si, s["kingdom"])
            col = BY_KEY[owner]["colors"][0]
            big = s["type"] in ("capital", "city", "castle", "town")
            rad = 5 if big else 3
            pygame.draw.circle(surf, col, (x, y), rad)
            pygame.draw.circle(surf, (240, 230, 200), (x, y), rad, 1)
            rect = pygame.Rect(x - 8, y - 8, 16, 16)
            self.map_rects.append((rect, si))
            if rect.collidepoint(mp) or big:
                yo = -18 if si % 2 else 10
                text(surf, s["name"], (x, y + yo), 11 if not rect.collidepoint(mp) else 14,
                     GOLD if rect.collidepoint(mp) else (220, 215, 200), center=True)
            if si in p.fiefs:
                pygame.draw.circle(surf, GOLD, (x, y), rad + 4, 2)
        for ar in g.society.armies:
            x = mx0 + int(ar.x / TILE * sc)
            pygame.draw.polygon(surf, BY_KEY[ar.kingdom]["colors"][0], [(x - 6, my0 + 214), (x + 6, my0 + 214),
                                                                          (x, my0 + 202)])
        px = mx0 + int(p.cx / TILE * sc)
        py = my0 + 20 + int((p.cy / TILE - 30) * (180 / 160))
        pygame.draw.circle(surf, (255, 255, 255), (px, py), 5)
        pygame.draw.circle(surf, (200, 30, 30), (px, py), 3)
        # politics
        y = my0 + 250
        text(surf, "Politik (politics)", (r.x + 20, y), 16, GOLD)
        wars = [f"{BY_KEY[a]['de']} ⚔ {BY_KEY[b]['de']}" for a, b in (tuple(w_) for w_ in g.society.wars)]
        text(surf, "[Krieg] War: " + (" · ".join(wars) if wars else "Frieden (peace)"), (r.x + 20, y + 24), 13)
        if p.liege:
            text(surf, f"You serve: {BY_KEY[p.liege]['de']}", (r.x + 20, y + 46), 13)
        if g.society.wanted:
            text(surf, "Outlawed in: " + ", ".join(BY_KEY[k]["de"] for k in g.society.wanted), (r.x + 20, y + 68), 13,
                 (240, 120, 100))
        yy = y + 96
        for kd in KINGDOMS:
            n = len(g.society.settlements_of(kd["key"]))
            text(surf, f"{kd['de']} — {kd['ruler']} — {n} settlements. {kd['blurb']}", (r.x + 20, yy), 11,
                 (190, 190, 180))
            yy += 16

    def draw_woerterbuch(self, surf):
        p = self.g.player
        r = parchment(surf, (120, 40, SCREEN_W - 240, SCREEN_H - 80))
        text(surf, "Mein Wörterbuch", (r.x + 24, r.y + 14), 26, INK, bold=True, shadow=False)
        m, l, tot = lingua.get().progress()
        text(surf, f"(my dictionary) — {len(p.dict.words)} Wörter · gemeistert (mastered) {m} · lerne (learning) {l}"
                   f" · Wortschatz {tot}. Q = Quiz, wheel = scroll, N = close",
             (r.x + 24, r.y + 50), 13, (90, 70, 50), shadow=False)
        if self.quiz is not None:
            q = self.quiz
            text(surf, "Was bedeutet… (what does this mean?)", (r.centerx, r.y + 120), 18, (90, 70, 50), center=True,
                 shadow=False)
            text(surf, q["de"], (r.centerx, r.y + 160), 40, (150, 60, 20), center=True, bold=True, shadow=False)
            for i, o in enumerate(q["opts"]):
                col = INK
                if q["result"] is not None:
                    col = (40, 120, 40) if o == q["en"] else (160, 60, 50)
                text(surf, f"{i + 1}. {o}", (r.centerx - 150, r.y + 240 + i * 34), 20, col, shadow=False)
            if q["result"] is not None:
                text(surf, ("Richtig! (correct)" if q["result"] else "Falsch! (wrong)") + " — any key 1-4 for the next",
                     (r.centerx, r.y + 400), 16, (90, 70, 50), center=True, shadow=False)
            text(surf, f"Punkte (score): {getattr(self, 'quiz_score', 0)}", (r.centerx, r.y + 440), 14,
                 (90, 70, 50), center=True, shadow=False)
            return
        words = p.dict.sorted()
        per_col = 24
        start = self.scroll * 3
        for i, (de, (en, n, ctx)) in enumerate(words[start:start + per_col * 3]):
            col, row = i // per_col, i % per_col
            x = r.x + 24 + col * ((r.w - 48) // 3)
            y = r.y + 80 + row * 22
            star = "★ " if lingua.get().stage(de) == 2 else ""
            text(surf, star + de, (x, y), 15, (130, 50, 20), bold=True, shadow=False)
            de = star + de
            wde = font(15, True).size(de)[0]
            text(surf, f" — {en}" + (f"  ×{n}" if n > 1 else ""), (x + wde, y + 1), 13, INK, shadow=False)

    def draw_stand(self, surf):
        g = self.g
        p = g.player
        r = parchment(surf, (60, 30, SCREEN_W - 120, SCREEN_H - 60))
        text(surf, "Die Ständeordnung", (r.x + 24, r.y + 12), 26, INK, bold=True, shadow=False)
        text(surf, "(the social order of 1300) — why each rank exists, and how to climb", (r.x + 24, r.y + 46), 13,
             (90, 70, 50), shadow=False)
        mp = pygame.mouse.get_pos()
        hov = None
        base_y = r.bottom - 60
        for i, rk in enumerate(RANKS):
            w_ = 640 - i * 56
            x = r.x + 40 + (640 - w_) // 2
            y = base_y - i * 46
            rect = pygame.Rect(x, y, w_, 40)
            cur = i == p.rank
            col = (200, 170, 110) if not cur else (230, 190, 90)
            if rect.collidepoint(mp):
                col = (215, 185, 130)
                hov = rk
            pygame.draw.rect(surf, col, rect, border_radius=4)
            pygame.draw.rect(surf, (120, 90, 60), rect, 2 if not cur else 3, border_radius=4)
            text(surf, f"{rk.de} ({rk.en})", (rect.centerx, rect.y + 4), 15, INK, center=True, bold=cur, shadow=False)
            text(surf, rk.estate, (rect.centerx, rect.y + 22), 11, (90, 70, 50), center=True, shadow=False)
            if cur:
                text(surf, "◀ du (you)", (rect.right + 8, rect.y + 10), 14, (150, 50, 20), shadow=False)
        rk = hov or rank_of(p.rank)
        ix = r.x + 760
        y = r.y + 90
        text(surf, f"{rk.de}", (ix, y), 24, (130, 50, 20), bold=True, shadow=False)
        text(surf, f"({rk.en}) — {rk.estate}", (ix, y + 32), 14, INK, shadow=False)
        rows = [("Lehen (fief)", rk.fief), ("Pflicht (duty)", rk.duty), ("Recht (privilege)", rk.privilege),
                ("Warum? (why)", rk.why), ("Anrede (address)", f"„{rk.address_de}“ ({rk.address_en}) — "
                                                            f"{'du (informal)' if rk.du else 'Ihr (formal)'}"),
                ("Befehl (command)", f"up to {rk.command} soldiers"),
                ("Bedarf (needs)", f"{rk.honour_needed} Ehre, {rk.money_needed} Pf")]
        y += 64
        for lab, val in rows:
            text(surf, lab, (ix, y), 13, (130, 50, 20), bold=True, shadow=False)
            y += 18
            words = val.split(" ")
            line = ""
            for wd in words:
                if font(13).size(line + wd)[0] > 380:
                    text(surf, line, (ix + 8, y), 13, INK, shadow=False)
                    y += 17
                    line = ""
                line += wd + " "
            text(surf, line, (ix + 8, y), 13, INK, shadow=False)
            y += 24
        y = r.y + 76
        text(surf, f"Ehre (honour): {p.ehre}   ·   Geld: {p.inv.money} Pf   ·   "
                   f"Lehnsherr: {BY_KEY[p.liege]['de'] if p.liege else '—'}   ·   "
                   f"Lehen: {', '.join(g.world.settlements[s]['name'] for s in p.fiefs) or '—'}",
             (r.x + 24, y), 13, INK, shadow=False)

    def draw_help(self, surf):
        r = parchment(surf, (100, 40, SCREEN_W - 200, SCREEN_H - 80))
        ltext(surf, "Help", (r.x + 24, r.y + 14), 26, INK, shadow=False, dark=True)
        lines = [
            ("A / D", "walk · Shift = run · S = crouch · run + S = slide · Space = jump · W = climb/swim up"),
            ("Mouse L / J", "attack — the move depends on your state: standing = 3-hit combo, running = charge,"),
            ("", "crouching = low sweep (and Konter after a block), in the air = plunge"),
            ("Mouse R / K", "block — tap just before a hit to PARRY (stuns the attacker, no stamina)"),
            ("Bow", "hold L to draw, aim with the mouse, release · V = fire arrows · wind & rain matter"),
            ("Hands", "axe on a tree: fell it · axe on a trunk: cut it · hammer/pick on a wall: break it · pick on ore"),
            ("E", "pick up (small → bag, big → arms) · set down · doors · chests · beds · Werkbank · talk · mount"),
            ("Carrying", "click: set it down where you point · Shift+click: fix it in place · R rotate · G throw"),
            ("C", "shape the log at your feet: Q/E choose a form, drag axe strokes along the dashed lines, Enter"),
            ("1-4 / wheel", "belt · Q = drop · T = cycle shield/armour/helmet from your bag"),
            ("I", "the Rucksack (bag) & crafting · Werkbank (E): shape wood precisely with the mouse"),
            ("B", "blueprints: huts, walls, gates, towers, chapels, halls, castles — raised piece by piece"),
            ("X / Tab / Z", "orders bar for your Haufen · Tab = select formation · Z = commander's zoomed-out view"),
            ("M", "world map, politics, fast travel by cart"),
            ("N", "Wörterbuch — every German word you've heard · Q = quiz"),
            ("R", "Ständeordnung — the social ladder and how to climb it"),
            ("Boat", "W/S = raise/lower sail · A/D = heading · Shift = row · Space = jump off"),
            ("F5 / F9", "save / load · Esc = pause"),
            ("Tactics", "Schildwall vs arrows · Igel (pikes) vs horses · Keil to break a line · Locker vs volleys"),
            ("", "Wechsel rotates tired front men · Flank a Haufen from behind to cut down its reserves"),
            ("World", "Fall into the Abyss and the sky spits you out elsewhere. Break what holds a wall up: it falls."),
        ]
        y = r.y + 64
        for k, v in lines:
            text(surf, k, (r.x + 30, y), 14, (130, 50, 20), bold=True, shadow=False)
            text(surf, v, (r.x + 170, y), 14, INK, shadow=False)
            y += 26

    def draw_pause(self, surf):
        s = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        s.fill((0, 0, 0, 150))
        surf.blit(s, (0, 0))
        text(surf, "Pause", (SCREEN_W // 2, 200), 44, GOLD, center=True, bold=True)
        opts = ["1. Resume", "2. Save", "3. Help", "4. Main menu"]
        self.pause_rects = []
        for i, o in enumerate(opts):
            rect = pygame.Rect(SCREEN_W // 2 - 160, 280 + i * 50, 320, 40)
            hov = rect.collidepoint(pygame.mouse.get_pos())
            panel(surf, rect, 220 if hov else 160)
            ltext(surf, o, (rect.centerx, rect.y + 9), 18, GOLD if hov else (230, 225, 210), center=True)
            surf.blit(pygame.Surface((0, 0)), (0, 0))
            self.pause_rects.append(rect)

    def draw_death(self, surf):
        s = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        s.fill((40, 0, 0, 170))
        surf.blit(s, (0, 0))
        text(surf, "Du bist gefallen.", (SCREEN_W // 2, 260), 44, (230, 200, 180), center=True, bold=True)
        text(surf, "(you have fallen)", (SCREEN_W // 2, 316), 18, (200, 180, 170), center=True)
        text(surf, "R — aufstehen (get up)   ·   Esc — Hauptmenü (main menu)", (SCREEN_W // 2, 380), 16,
             (220, 210, 200), center=True)

    def draw_card(self, surf):
        c = self.card
        s = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        s.fill((0, 0, 0, 170))
        surf.blit(s, (0, 0))
        r = parchment(surf, (SCREEN_W // 2 - 400, 70, 800, SCREEN_H - 140))
        text(surf, c["title"], (r.centerx, r.y + 26), 32, INK, center=True, bold=True, shadow=False)
        y = r.y + 74
        if c.get("subtitle"):
            text(surf, c["subtitle"], (r.centerx, y), 15, (110, 80, 50), center=True, shadow=False)
            y += 34
        for line in c["lines"]:
            if not line:
                y += 12
                continue
            y += bilingual(surf, line, (r.centerx, y), 17, 700, center=True, dark=True) + 6
        text(surf, "— Leertaste (space) —", (r.centerx, r.bottom - 34), 13, (120, 90, 60), center=True, shadow=False)
