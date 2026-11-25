"""Die Chronik des Konrad — the story mode.

Anno Domini 1300. The world is a long strip of land between two ends: in the west the Abyss,
where the land breaks off into nothing; in the east the Fire Sea, where it burns away.
The Kaiser is dead. Seven princes — the Kurfürsten — must elect a new one, and cannot agree.
And every winter, the Abyss eats a little more of the land.

Konrad, a serf of Erlenbach at the very brink of the world, will rise from the mud to the
council of kings — and learn why the Abyss is hungry.

Engine: each chapter is a list of steps. A step has an objective type, parameters, on-start
actions and dialogue. The engine listens to session events (talk, death, build, craft, ...).
"""
import math

import pygame

from ..settings import TILE, SCREEN_W, GOLD, DAY_LENGTH, SEA_LEVEL
from ..entities.humanoid import Humanoid
from ..combat.formation import Haufen
from ..society.names import make_look
from ..society.kingdoms import BY_KEY
from ..ui.common import text, panel, bilingual

PROLOG = [
    "[Anno Domini|in the year of the Lord] 1300.",
    "The world is a long strip of land between two ends.",
    "In the west lies [der Abgrund|the abyss], where the earth breaks off into nothing.",
    "In the east burns [das Glutmeer|the fire sea], where it melts away.",
    "Between them lie seven realms. Their rulers are the seven [Kurfürsten|prince-electors].",
    "The [Kaiser|emperor] is dead, and they cannot agree on a new one.",
    "And every [Winter|winter], the [Abgrund|abyss] eats a little more of the land.",
    "",
    "In Erlenbach, the last village before the brink, a [Leibeigener|serf] named Konrad wakes.",
]


def step(kind, text_, **kw):
    d = dict(kind=kind, text=text_)
    d.update(kw)
    return d


CHAPTERS = [
    dict(title="I. Der Leibeigene", sub="(The Serf)", intro=[
        "Konrad belongs to the land, and the land belongs to Graf Randolf.",
        "His [Vogt|bailiff], Gerold, collects the [Zehnt|tithe] — a tenth of every harvest.",
        "Old Ulf, who once fought for the Graf, watches the road and the brink.",
        "", "W A S D to move · E to talk · H for help"],
        steps=[
            step("talk", "Talk to old Ulf by the palisade. ([Rede|talk] with E)", tag="ulf", lines=[
                "Ulf: Konrad! [Aufwachen|wake up]! The [Sonne|sun] is high.",
                "Ulf: The [Vogt|bailiff] wants the [Zehnt|tithe] today. Eight sheaves of [Weizen|wheat].",
                "Ulf: The [Felder|fields] are ripe. Walk up to the golden [Ähren|ears] and press E to reap."]),
            step("collect", "Harvest 8 [Weizen|wheat] in the fields (E on ripe wheat).", item="wheat", n=8),
            step("deliver", "Bring 8 [Weizen|wheat] to Vogt Gerold.", tag="vogt", item="wheat", n=8, lines=[
                "Gerold: Eight sheaves. [Gut|good]. The [Herr|lord] thanks you — I don't.",
                "Gerold: One tenth for the [Kirche|church], the rest for the [Graf|count]. That is the law.",
                "Gerold: Now go. And keep away from the [Rand|edge], [Bursche|lad]."]),
            step("talk", "Ulf wants to teach you to fight. Talk to him.", tag="ulf", give={"knueppel": 1}, lines=[
                "Ulf: Robbers have been seen in the [Wald|forest]. You should know how to fight.",
                "Ulf: Take this [Knüppel|cudgel]. Put it in your hand (1-0 keys).",
                "Ulf: Hold the right mouse button to [blocken|block]. Tap it right before my blow lands — that's a "
                "[Parade|parry].",
                "Ulf: Then [ducken|crouch] and strike: a [Konter|counter]. Come on — [Angriff|attack]!"]),
            step("spar", "Spar with Ulf until he yields. Try a parry (tap right mouse just before his hit).",
                 tag="ulf", lines=["Ulf: [Genug|enough]! [Gut gemacht|well done]. You have quick hands."]),
            step("event", "", action="crumble"),
            step("reach_tag", "[Hilfe|help]! Little Greta ran to the edge of the world! Find her in the west.",
                 tag="greta", dist=60, lines=["Greta: The [Boden|ground] is shaking! I'm [Angst|afraid]!",
                                              "Konrad: Take my [Hand|hand]. [Komm|come]. We go home."]),
            step("escort", "Bring Greta back to Erlenbach.", tag="greta", place="Erlenbach"),
            step("battle", "[Räuber|robbers]! Kuno's men raid Erlenbach! Lead the [Bauern|peasants]. "
                           "(C = orders, try 'Angriff!')", action="raid"),
            step("talk", "Talk to Ulf.", tag="ulf", lines=[
                "Ulf: You fought like a [Ritter|knight]. But the [Vogt|bailiff] says it was your fault.",
                "Ulf: He wants you flogged for 'leading serfs to arms'. That is a [Verbrechen|crime] for a "
                "[Leibeigener|serf].",
                "Ulf: Listen. [Stadtluft macht frei|city air makes you free]. Live in a free city for a "
                "[Jahr und Tag|year and a day], and no lord can claim you.",
                "Ulf: Jakob the merchant leaves for Lübenau tonight. Go with him. [Geh|go]!"]),
        ]),
    dict(title="II. Stadtluft macht frei", sub="(City air makes you free)", intro=[
        "Three days east with Jakob's wagon, through the endless [Wald|forest] of Waldheim,",
        "past the mountains of Hochburg, to the free city on the sea: Lübenau.",
        "No lord rules here. Merchants and guilds govern themselves."],
        teleport="Lübenau", steps=[
            step("talk", "Speak to Bürgermeister Hinrich Witte in Lübenau.", tag="mayor", lines=[
                "Witte: A runaway [Leibeigener|serf]? Hm. The law of the [Reich|empire] is clear:",
                "Witte: A [Jahr und Tag|year and a day] within our walls, and you are [frei|free].",
                "Witte: But in Lübenau nobody eats for free. Find [Arbeit|work]. The [Schmied|smith] needs iron."]),
            step("deliver", "The smith needs 3 [Eisenbarren|iron bars]. Buy or smelt them (Ofen: 2 ore + coal), "
                            "then bring them to the smith.", tag="smith", item="iron_ingot", n=3,
                 give={"schwert": 1, "silver_coin": 20}, lines=[
                     "Schmied: [Ausgezeichnet|excellent] iron! Here — a [Schwert|sword] I could not sell.",
                     "Schmied: And twenty [Pfennig|pennies]. A man should be paid for honest work."]),
            step("money", "Earn 60 [Pfennig|pennies] (trade at the market, work for townsfolk).", n=60),
            step("event", "", action="year_and_day"),
            step("rank", "Buy your [Bürgerrecht|citizenship] from the Bürgermeister (60 Pf).", n=2),
        ]),
    dict(title="III. Der Knappe", sub="(The Squire)", intro=[
        "A knight rides into Lübenau: Ulrich von Steinach, hunter of robber knights.",
        "His squire fell to Kuno der Schwarze — the same Kuno whose men burned Erlenbach."],
        steps=[
            step("talk", "Find Ritter Ulrich in Lübenau.", tag="ulrich", action="spawn_ulrich", lines=[
                "Ulrich: You are the [Bauer|peasant] who beat Kuno's men with a [Dreschflegel|flail]? Ha!",
                "Ulrich: I need a [Knappe|squire]. Show me what you can do. [Zieh dein Schwert|draw your sword]!"]),
            step("spar", "Spar with Ritter Ulrich.", tag="ulrich", lines=[
                "Ulrich: [Genug|enough]! Kneel. From today you carry my [Schild|shield]. You are my "
                "[Knappe|squire]."], action_after="squire"),
            step("mount", "Ulrich gives you a [Pferd|horse]. Mount it (E).", action="give_horse"),
            step("event", "", action="ride_to_kuno"),
            step("kill_tag", "Storm Schwarzfels and defeat [Raubritter|robber knight] Kuno!", tag="kuno"),
            step("event", "", action="knighting"),
        ]),
    dict(title="IV. Das Lehen", sub="(The Fief)", intro=[
        "Graf Randolf grants the new knight a [Lehen|fief] in thanks: the village of Erlenbach.",
        "The serf returns as its lord. Gerold the [Vogt|bailiff] kneels in the mud."],
        teleport="Erlenbach", steps=[
            step("talk", "Talk to Vogt Gerold.", tag="vogt", give={"brick": 140, "planks": 80, "slate": 40,
                                                                   "wood": 30, "straw": 20}, lines=[
                "Gerold: H-[Herr Ritter|Sir Knight]… [Verzeiht mir|forgive me]. I only followed the law.",
                "Konrad: Then follow it now. The village needs [Mauern|walls] before Kuno's friends return.",
                "Gerold: The [Bauern|peasants] brought [Steine|stones] and [Holz|timber], [Herr|lord]."]),
            step("build", "Build a [Wachturm|watchtower] in Erlenbach (B = blueprints).", names=["Wachturm"]),
            step("build", "Build a [Mauer|wall] or [Tor|gate] to close the village.", names=["Mauer", "Tor",
                                                                                         "Palisade"]),
            step("talk", "A monk has arrived. Talk to Bruder Anselm.", tag="anselm", action="spawn_anselm", lines=[
                "Anselm: [Friede sei mit dir|peace be with you], Herr Konrad. I have walked the brink for years.",
                "Anselm: Every war between the realms, the [Abgrund|abyss] grows. Every peace, it rests.",
                "Anselm: In Frostholm, across the Grey Sea, the queen keeps the oldest [Chronik|chronicle].",
                "Anselm: It may tell us why. Will you sail with me?"]),
        ]),
    dict(title="V. Über das Graue Meer", sub="(Across the Grey Sea)", intro=[
        "In Lübenau harbour waits a [Kogge|cog], a fat-bellied sailing ship.",
        "The wind decides how fast you sail. Against it, you crawl. In a storm, lower the [Segel|sail]!"],
        teleport="Lübenau Hafen", steps=[
            step("board", "Board your [Kogge|cog] at the end of the dock (E).", action="give_boat"),
            step("reach_x", "Sail east to Frostholm. W = [Segel|sail] up, S = down, A/D = heading, "
                            "Shift = [rudern|row].", place="Eisvik"),
            step("reach_tag", "Find Königin Sigrun in her castle at Frostholm.", tag="sigrun", dist=50, lines=[
                "Sigrun: A knight from the brink of the world. The chronicle you seek is lost —",
                "Sigrun: taken by [Wölfe|wolves]' masters, the outlaws of Wolfsheim cave. Bring it back."]),
            step("collect", "Recover the [Chronik|chronicle] from the cave beneath Wolfsheim.", item="chronik", n=1,
                 action="hide_chronicle"),
            step("reach_tag", "Return the chronicle to Königin Sigrun.", tag="sigrun", dist=50, lines=[
                "Sigrun: [Danke|thank you]. Listen to what the first chroniclers wrote:",
                "Sigrun: „[Wenn sieben Stimmen eins werden, schweigt der Abgrund|when seven voices become one, "
                "the abyss falls silent].“",
                "Sigrun: Seven voices — the seven [Kurfürsten|electors]. Only a true election will stop it.",
                "Sigrun: But Markgraf Otto der Rote wants the crown by the [Schwert|sword]. He marches on "
                "Heiligenstein."]),
        ]),
    dict(title="VI. Die Glut", sub="(The Ember)", intro=[
        "Markgraf Otto der Rote of Glutmark has crossed the strait with fire and steel.",
        "If Heiligenstein falls, the Bishop's vote falls with it — and Otto takes the crown.",
        "The Bishop gives you command of his host. Use everything you have learned."],
        teleport="Heiligenstein", steps=[
            step("battle", "Defeat Otto's army before Heiligenstein! (C = orders, Tab = select)", action="glut_battle"),
        ]),
    dict(title="VII. Die Wahl", sub="(The Election)", intro=[
        "The seven [Kurfürsten|electors] meet in the great hall of Hochburg.",
        "Otto der Rote, defeated, comes in chains — but his vote still counts."],
        teleport="Hochburg", steps=[
            step("event", "", action="election"),
        ]),
]


class Story:
    def __init__(self, s):
        self.s = s
        self.ch = 0
        self.si = -1
        self.cur = None
        self.npcs = {}
        self.flags = {}
        self.timer = 0.0
        self.done = False

    # ------------------------------------------------------------------ helpers
    def settlement(self, name):
        return next(s for s in self.s.world.settlements if s["name"] == name)

    def sx(self, name, frac=0.5):
        s = self.settlement(name)
        return (s["x0"] + (s["x1"] - s["x0"]) * frac) * TILE

    def ground_px(self, x):
        w = self.s.world
        tx = int(x // TILE)
        st = w.settlement_at(tx)
        start = st["g"] * TILE - 40 if st else w.surface_y(x) - 60
        return w.ground_y(x, start, 300)

    def spawn_npc(self, tag, name, x, rank=1, job="farmer", gear=("fists", "", "kleidung", ""), faction=None,
                  brain="idle", lines=None, look=None, female=False, kingdom="randmark"):
        s = self.s
        if tag in self.npcs and not self.npcs[tag].dead and not self.npcs[tag].removed:
            return self.npcs[tag]
        kd = BY_KEY.get(kingdom)
        lk = look or make_look(s.rng, rank, job, female, kd["colors"] if kd else None)
        gy = self.ground_px(x)
        h = Humanoid(x - 7, gy - 43, lk, faction or kingdom, name, rank)
        h.equip(weapon=gear[0], shield=gear[1], armor=gear[2], helmet=gear[3])
        h.story_tag = tag
        h.anchor = x
        h.keep = True
        h.idle_lines = lines
        h.skill = 0.6
        h.home_brain = brain
        s.add_humanoid(h, brain)
        self.npcs[tag] = h
        return h

    def card(self, title, lines, then=None, sub=None):
        self.s.ui.show_card(title, lines, on_close=then, subtitle=sub)

    def teleport(self, name, frac=0.3):
        s = self.s
        p = s.player
        x = self.sx(name, frac)
        gy = self.ground_px(x)
        p.x, p.y = x, gy - p.h - 1
        p.vx = p.vy = 0
        p.fall_peak = p.y
        if p.mount is not None:
            p.mount.x, p.mount.y = p.x - 10, p.y
        for f in p.followers:
            f.x, f.y = p.x - 40, p.y
        s.camera.snap(p.cx, p.cy)
        s.lod_t = 0
        s.update_lod(0.0)

    # ------------------------------------------------------------------ flow
    def begin(self):
        s = self.s
        p = s.player
        p.name = "Konrad"
        p.look["tunic"] = (110, 96, 72)
        # ripen Erlenbach's fields for the first task
        er = self.settlement("Erlenbach")
        w = s.world
        for b in er["buildings"]:
            if b["kind"] == "field" and b.get("plot") is not None:
                for st in w.plots[b["plot"]].strips:
                    st[0], st[1], st[2], st[4] = "wheat", 1.0, True, 0.0
        s.env.time = DAY_LENGTH * 0.29
        self.spawn_npc("ulf", "Ulf der Alte", self.sx("Erlenbach", 0.08), rank=1, job="guard",
                       gear=("speer", "holzschild", "gambeson", "kettenhaube"),
                       lines=["[Wach bleiben|stay awake], Konrad.", "My [Knie|knees] hurt when [Regen|rain] comes."])
        self.spawn_npc("vogt", "Vogt Gerold", self.sx("Erlenbach", 0.55), rank=2, job="lord",
                       gear=("dolch", "", "kleidung", ""),
                       lines=["The [Zehnt|tithe]! Don't forget the [Zehnt|tithe]!", "[Arbeit|work], not talk!"])
        self.card("Die Chronik des Konrad", PROLOG, then=self.next_chapter, sub="(the chronicle of Konrad)")

    def next_chapter(self):
        if self.ch >= len(CHAPTERS):
            return
        c = CHAPTERS[self.ch]
        self.si = -1

        def go():
            if c.get("teleport"):
                self.teleport(c["teleport"])
            self.advance()

        self.card(c["title"], c["intro"], then=go, sub=c["sub"])

    def advance(self):
        c = CHAPTERS[self.ch]
        self.si += 1
        if self.si >= len(c["steps"]):
            self.ch += 1
            if self.ch < len(CHAPTERS):
                self.s.sfx("bell")
                self.next_chapter()
            else:
                self.done = True
            return
        self.cur = c["steps"][self.si]
        self.progress = 0
        self.timer = 0.0
        self.start_step(self.cur)

    def complete(self, lines=None):
        st = self.cur
        if st is None:
            return
        self.cur = None
        give = st.get("give")
        p = self.s.player
        if give:
            for k, n in give.items():
                p.inv.add(k, n)
                self.s.pickup_text(k, n)
            self.s.sync_held()
        after = st.get("action_after")
        if after:
            self.do_action(after)
        lines = lines if lines is not None else st.get("lines")
        if lines:
            self.card("", lines, then=self.advance)
        else:
            self.advance()

    # ------------------------------------------------------------------ step starts / actions
    def start_step(self, st):
        k = st["kind"]
        s = self.s
        if k == "event":
            self.do_action(st["action"])
            return
        if st.get("action"):
            self.do_action(st["action"])
        if k == "spar":
            h = self.npcs.get(st["tag"])
            if h:
                h.duel = True
                h.spar = True
                h.brave = True
                h.hp = h.max_hp
                s.set_brain(h, "combat", target=s.player)
        if st.get("text"):
            s.ui.toast(st["text"], 6)

    def do_action(self, a):
        s = self.s
        p = s.player
        w = s.world
        if a == "crumble":
            s.camera.shake = 12
            s.sfx("collapse")
            # a chunk of the brink falls away
            from ..poly.objects import PhysObject
            x = w.abyss_w
            while x < w.w and w.bottom[x] - w.top[x] < 4:
                x += 1
            for xx in range(x, x + 14):
                top = float(w.top[xx])
                for k in range(3):
                    if s.rng.random() < 0.5:
                        r = s.rng.uniform(8, 16)
                        PhysObject.spawn(w, [(-r, -r * 0.6), (r * 0.8, -r), (r, r * 0.5), (-r * 0.6, r)],
                                         xx * TILE + 8, top + 20 + k * 40, "rock", "debris", debris=True)
            w.top[x:x + 14] = w.bottom[x:x + 14]
            w.set_surface(x, x + 14, w.bottom[x:x + 14].copy())
            gx = (w.abyss_w + 40) * TILE
            self.spawn_npc("greta", "Greta", gx, rank=0, job="child", female=True,
                           lines=["[Hilfe|help]!", "[Mama|mum]!"])
            s.ui.toast("The earth groans. Somewhere in the west, a child screams: „[Hilfe|help]!“", 6)
            self.advance()
        elif a == "raid":
            ex = self.sx("Erlenbach", 1.0) + 900
            hf = Haufen(s, "bandit", "raeuber", 14, ex, -1, ((50, 44, 40), (180, 30, 30)))
            hf.order = "vorwaerts"
            s.formations.append(hf)
            self.raid = [hf]
            for i in range(8):
                h = self.spawn_npc(f"bauer{i}", "Bauer", p.cx - 40 - i * 18, rank=0, job="farmer",
                                   gear=(["flegel", "mistgabel", "knueppel", "axt"][i % 4], "", "kleidung", ""),
                                   faction="player", brain="follow")
                h.follow_idx = i
                h.brave = True
                p.followers.append(h)
            s.ui.toast("Eight [Bauern|peasants] follow you. Press C, then [Formiert euch|form up] (−) to "
                       "make them a [Haufen|formation].", 8)
            s.sfx("horn")
        elif a == "year_and_day":
            s.ui.fade("[Ein Jahr und ein Tag|a year and a day] later…")
            s.env.time += DAY_LENGTH * 8
            p.freed_by_city = True
            p.rank = max(p.rank, 1)
            p.free = True
            self.card("Frei!", ["The city [Rat|council] writes your name in the book of free men.",
                                "No lord can claim you now. You are a [Freier|free man].",
                                "Now buy your [Bürgerrecht|citizenship] from the Bürgermeister."],
                      then=self.advance, sub="(free!)")
        elif a == "squire":
            p.rank = max(p.rank, 3)
            p.liege = "waldheim"
            p.ehre += 20
            p.update_look_for_rank(BY_KEY["waldheim"]["colors"])
        elif a == "spawn_ulrich":
            u = self.spawn_npc("ulrich", "Ritter Ulrich", p.cx + 160, rank=4, job="knight",
                               gear=("langschwert", "", "plattenrock", "topfhelm"), kingdom="waldheim",
                               lines=["A [Knappe|squire]… I need a [Knappe|squire].",
                                      "Kuno der Schwarze will [bezahlen|pay] for my boy."])
            u.max_hp = u.hp = 220
            u.look["crest"] = (40, 96, 54)
        elif a == "spawn_anselm":
            self.spawn_npc("anselm", "Bruder Anselm", p.cx + 120, rank=1, job="monk",
                           look=make_look(s.rng, 1, "monk", clergy=True),
                           lines=["[Friede|peace].", "The [Abgrund|abyss] listens, Herr Konrad."])
        elif a == "give_horse":
            horse = s.spawn_horse(p.cx + 40, p.feet, wild=False)
            horse.owner = p
            horse.keep = True
        elif a == "ride_to_kuno":
            s.ui.fade("Ulrich's company rides west for six days…")
            sch = self.settlement("Schwarzfels")
            x = (sch["x0"] - 120) * TILE
            gy = self.ground_px(x)
            p.x, p.y = x, gy - p.h - 1
            if p.mount:
                p.mount.x, p.mount.y = p.x - 10, p.y
            s.camera.snap(p.cx, p.cy)
            s.update_lod(0.0)
            colors = BY_KEY["waldheim"]["colors"]
            hx = x - 40
            for unit, n in (("schild", 18), ("leiter", 16), ("armbrust", 12)):
                hf = Haufen(s, "player", unit, n, hx, 1, colors, leader=p)
                hf.order = "halt"
                s.formations.append(hf)
                p.haufen.append(hf)
                hx -= hf.width() + 30
            ram = s.spawn_engine("ramm", x + 120, "player", 1, colors)
            ram.active = False
            ram.keep = True
            u = self.spawn_npc("ulrich", "Ritter Ulrich", x + 30, rank=4, job="knight",
                               gear=("langschwert", "", "plattenrock", "topfhelm"), faction="player",
                               brain="follow", kingdom="waldheim")
            u.x, u.y = x + 30, gy - 43
            u.faction = "player"
            u.duel = False
            u.brave = True
            s.set_brain(u, "follow")
            if u not in p.followers:
                p.followers.append(u)
            # Kuno and his men
            kuno = self.spawn_npc("kuno", "Kuno der Schwarze", (sch["x0"] + 40) * TILE, rank=4, job="raubritter",
                                  gear=("langschwert", "", "plattenrock", "topfhelm"), faction="bandit",
                                  brain="combat", lines=["Come and die, [Bauer|peasant]!"])
            kuno.look["tunic"] = (30, 28, 30)
            kuno.look["crest"] = (30, 28, 30)
            kuno.max_hp = kuno.hp = 260
            kuno.anchor = kuno.cx
            for unit, n, off in (("raeuber", 22, 10), ("bogen", 12, 36)):
                hf = Haufen(s, "bandit", unit, n, (sch["x0"] + off) * TILE, -1, ((40, 36, 34), (160, 30, 30)))
                hf.order = "halt"
                hf.no_advance = True
                s.formations.append(hf)
            s.society.wanted.discard("bandit")
            s.ui.toast("Schwarzfels: a [Graben|moat] and a [Zugbrücke|drawbridge]. Order [Vorwärts|forward] (C): "
                       "your men fill the moat, the [Leiterträger|ladder men] climb. E at the [Rammbock|ram] sends it "
                       "against the gate.", 10)
        elif a == "knighting":
            p.rank = max(p.rank, 4)
            p.liege = "randmark"
            s.society.make_peace("waldheim", "randmark")
            er = self.settlement("Erlenbach")
            si = s.world.settlements.index(er)
            if si not in p.fiefs:
                p.fiefs.append(si)
            p.ehre += 40
            p.update_look_for_rank(BY_KEY["randmark"]["colors"])
            p.equip(armor="kettenhemd", helmet="topfhelm", shield="dreieckschild")
            for hf in p.haufen:
                hf.dead = True
            self.card("Der Ritterschlag", [
                "In the ruins of Schwarzfels, Ritter Ulrich draws his sword.",
                "He strikes your shoulder once: „[Erhebt Euch, Ritter Konrad|rise, Sir Konrad]!“",
                "Graf Randolf of Randmark, freed from Kuno's raids, makes peace with Waldheim",
                "and grants you a [Lehen|fief]: the village of Erlenbach — where you were born a "
                "[Leibeigener|serf].", "", "You are now a [Ritter|knight] (rank 4). Press R to see the "
                                           "[Ständeordnung|social order]."], then=self.advance,
                sub="(the accolade)")
            s.sfx("bell")
        elif a == "give_boat":
            from ..entities.boat import Boat
            port = self.settlement("Lübenau Hafen")
            dock = next(b for b in port["buildings"] if b["kind"] == "dock")
            boat = next((b for b in s.boats if getattr(b, "settlement", None) is not None), None)
            if boat is None:
                boat = Boat(dock["berth"] * TILE - 56, SEA_LEVEL * TILE - 12, colors=BY_KEY["randmark"]["colors"])
                s.boats.append(boat)
            boat.owner = p
            boat.for_sale = False
            boat.settlement = None
            boat.keep = True
            boat.facing = 1
            a_ = self.spawn_npc("anselm", "Bruder Anselm", p.cx - 30, rank=1, job="monk",
                                look=make_look(s.rng, 1, "monk", clergy=True), faction="player", brain="follow",
                                lines=["[Gott|God] guide our [Segel|sail]."])
            p.followers.append(a_)
        elif a == "hide_chronicle":
            wolf = self.settlement("Wolfsheim")
            cx = wolf["x1"] + 40
            g = int(s.world.surface[cx])
            # carve a cave going down and put the chest at its end
            from shapely.geometry import LineString
            from ..poly.prefab import Decor
            X, G = cx * TILE, s.world.surface_y(cx * TILE)
            path = [(X, G - 10), (X + 10 * TILE, G + 9 * TILE), (X + 26 * TILE, G + 22 * TILE),
                    (X + 40 * TILE, G + 24 * TILE)]
            s.world.add_cave(LineString(path).buffer(26, quad_segs=3))
            cy = G + 24 * TILE + 22
            chest = Decor("chest", X + 36 * TILE, cy, 14, 10, items={"chronik": 1, "silver_coin": 40})
            chest.data["fresh"] = False
            s.world.index_add("decor_chunks", chest.x, chest)
            lamp = Decor("lantern", X + 30 * TILE, cy - 26, 6, 10)
            s.world.index_add("decor_chunks", lamp.x, lamp)
            from ..entities.animals import Animal
            for i in range(3):
                a2 = Animal(X + (28 + i * 3) * TILE, G + 22 * TILE, "wolf")
                s.animals.append(a2)
            s.ui.toast("The cave mouth gapes just east of Wolfsheim. Bring a [Fackel|torch].", 7)
        elif a == "glut_battle":
            colors = BY_KEY["heiligenstein"]["colors"]
            hs = self.settlement("Heiligenstein")
            x = (hs["x1"] + 30) * TILE
            gy = self.ground_px(x)
            p.x, p.y = x, gy - p.h - 1
            s.camera.snap(p.cx, p.cy)
            hx = x + 120
            for unit, n in (("spiess", 40), ("schild", 30), ("bogen", 30), ("ritter", 12)):
                hf = Haufen(s, "player", unit, n, hx, 1, colors, leader=p)
                hf.order = "halt"
                s.formations.append(hf)
                p.haufen.append(hf)
                hx -= hf.width() + 30
            ex = x + 1400
            ocol = BY_KEY["glutmark"]["colors"]
            self.glut = []
            for unit, n in (("ritter", 16), ("reisige", 10), ("speer", 40), ("schild", 30), ("bauern", 40),
                            ("armbrust", 24)):
                hf = Haufen(s, "glutmark", unit, n, ex, -1, ocol)
                hf.order = "halt"
                s.formations.append(hf)
                self.glut.append(hf)
                ex += hf.width() + 30
            for k in range(2):
                gun = s.spawn_engine("buechse", ex + 80 + k * 70, "glutmark", -1, ocol)
                gun.active = True
            s.ui.toast("Otto brings [Donnerbüchsen|thunder-guns] — iron pots that roar fire. Hit them before they "
                       "find their range!", 8)
            p.liege = "heiligenstein" if p.liege is None else p.liege
            s.society.declare_war("glutmark", p.liege)
            s.society.wars.add(frozenset(("glutmark", "heiligenstein")))
            s.ui.toast("Otto's host approaches from the east. Pikes in [Igel|hedgehog] against his knights!", 8)
            s.sfx("horn")
        elif a == "election":
            p.rank = max(p.rank, 6)
            p.update_look_for_rank(BY_KEY[p.liege]["colors"] if p.liege in BY_KEY else None)
            for w_ in list(s.society.wars):
                s.society.wars.discard(w_)
            self.flags["peace"] = True
            lines = [
                "The seven [Kurfürsten|electors] sit at one table for the first time in a generation.",
                "Graf Randolf of Randmark. Herzog Eberhard of Waldheim. König Albrecht of Hochburg.",
                "Fürstbischof Wolfram of Heiligenstein. Bürgermeister Witte for Lübenau.",
                "Königin Sigrun of Frostholm. And Otto der Rote, in chains, of Glutmark.",
                "",
                "You — once a [Leibeigener|serf] of Erlenbach — read the chronicle aloud:",
                "„[Wenn sieben Stimmen eins werden, schweigt der Abgrund|when seven voices become one, the abyss "
                "falls silent].“",
                "",
                "One by one, they cast their [Stimme|vote]. Seven voices, one name.",
                "In the far west, the trembling at the brink stops.",
                "",
                "You are raised to [Graf|count]. The [Chronik|chronicle] ends — the world goes on.",
                "(The sandbox is yours: keep playing.)"]
            self.card("Die Wahl", lines, then=self.advance, sub="(the election)")
            s.sfx("bell")

    # ------------------------------------------------------------------ event handling
    def on_event(self, name, kw):
        st = self.cur
        if st is None:
            return
        k = st["kind"]
        if k == "kill_tag" and name == "death" and getattr(kw.get("h"), "story_tag", None) == st["tag"]:
            self.complete()
        elif k == "build" and name == "built" and kw.get("name") in st["names"]:
            self.complete()
        elif k == "mount" and name == "mount":
            self.complete()
        elif k == "board" and name == "board":
            self.complete()

    def dialogue_options(self, npc):
        st = self.cur
        tag = getattr(npc, "story_tag", None)
        opts = []
        if st is None:
            return opts
        k = st["kind"]
        match_tag = tag is not None and st.get("tag") == tag
        if st.get("tag") == "mayor" and getattr(npc, "person", None) and npc.person.job in ("mayor", "ruler") and \
                npc.person.kingdom == "luebenau":
            match_tag = True
        if st.get("tag") == "smith" and getattr(npc, "person", None) and npc.person.job == "smith":
            s_ = self.s.world.settlement_at(int(npc.cx // TILE), margin=10)
            match_tag = s_ is not None and "Lübenau" in s_["name"]
        if st.get("tag") == "sigrun" and getattr(npc, "person", None) and npc.person.job == "ruler" and \
                npc.person.kingdom == "frostholm":
            match_tag = True
        if not match_tag:
            return opts
        if k == "talk":
            opts.append(("» [Weiter|continue]", lambda: (self._close(), self.complete())))
        elif k == "deliver":
            def deliver():
                p = self.s.player
                if p.inv.count(st["item"]) >= st["n"]:
                    p.inv.remove(st["item"], st["n"])
                    self.s.sync_held()
                    self._close()
                    self.complete()
                else:
                    self.s.ui.set_line(f"You don't have enough yet ({p.inv.count(st['item'])}/{st['n']}).")
            opts.append((f"» Give {st['n']}× {st['item']}", deliver))
        elif k == "reach_tag":
            opts.append(("» [Weiter|continue]", lambda: (self._close(), self.complete())))
        return opts

    def _close(self):
        self.s.ui.modal = None
        self.s.ui.npc = None

    def update(self, dt):
        st = self.cur
        s = self.s
        p = s.player
        self.timer += dt
        # the brink keeps crumbling until peace is made
        if self.flags.get("peace"):
            s.crumble_t = 999
        if st is None:
            return
        k = st["kind"]
        if k == "collect" and p.inv.count(st["item"]) >= st["n"]:
            self.complete()
        elif k == "money" and p.inv.money >= st["n"]:
            self.complete()
        elif k == "rank" and p.rank >= st["n"]:
            self.complete()
        elif k == "spar":
            h = self.npcs.get(st["tag"])
            if h is not None and (h.hp < h.max_hp * 0.45 or h.dead):
                h.duel = False
                h.dead = False
                h.hp = h.max_hp
                h.state = "idle"
                s.set_brain(h, "idle")
                h.say("[Ich gebe auf|I yield]!", t=3)
                s.hear("[Ich gebe auf|I yield]!", "story")
                p.ehre += 5
                self.complete()
            elif p.hp < p.max_hp * 0.25:
                p.hp = p.max_hp * 0.6
                if h is not None:
                    h.hp = h.max_hp
                    h.say("Again! [Noch einmal|once more]!", t=3)
        elif k == "reach_tag":
            h = self.npcs.get(st["tag"])
            if h is None and st["tag"] == "sigrun":
                h = next((x for x in s.humanoids if getattr(x, "person", None) and x.person.job == "ruler"
                          and x.person.kingdom == "frostholm"), None)
            if h is not None and abs(h.cx - p.cx) < st.get("dist", 60) and abs(h.cy - p.cy) < 80:
                if st["tag"] == "greta":
                    h.faction = "player"
                    s.set_brain(h, "follow")
                    h.follow_idx = len(p.followers)
                    p.followers.append(h)
                self.complete()
        elif k == "escort":
            h = self.npcs.get(st["tag"])
            er = self.settlement(st["place"])
            if h is not None and er["x0"] * TILE < h.cx < er["x1"] * TILE:
                if h in p.followers:
                    p.followers.remove(h)
                s.set_brain(h, "idle")
                h.anchor = h.cx
                h.say("[Danke|thank you], Konrad!", t=4)
                s.hear("[Danke|thank you], Konrad!", "story")
                p.ehre += 5
                self.complete(["Greta's mother weeps: „[Danke|thank you]! [Gott segne dich|God bless you]!“",
                               "Even Vogt Gerold nods. Barely."])
        elif k == "reach_x":
            sett = self.settlement(st["place"])
            if p.cx > sett["x0"] * TILE - 400:
                self.complete(["Land! The snowy cliffs of Frostholm rise from the sea.",
                               "[Willkommen|welcome] to the Island Kingdom."])
            # a storm halfway across
            mid = [r for r in s.world.regions if r[2] == "ocean"][0]
            if not self.flags.get("storm") and p.cx > (mid[0] + (mid[1] - mid[0]) * 0.4) * TILE:
                self.flags["storm"] = True
                s.env.force("sturm")
                s.env.wind_target = 1.0
                s.ui.toast("[Sturm|storm]! Lower the [Segel|sail] (S) or you will capsize!", 8)
        elif k == "battle":
            if st.get("action") == "raid":
                left = [h for h in self.raid if not h.dead and not h.routed]
                if not left and self.timer > 3:
                    p.ehre += 10
                    for f in list(p.followers):
                        if getattr(f, "story_tag", "").startswith("bauer"):
                            f.removed = True
                    for hf in p.haufen:
                        hf.dead = True
                    self.complete(["The robbers flee into the [Wald|forest]!",
                                   "„[Sieg|victory]!“ shout the peasants. Two of them will not shout again."])
            else:
                left = [h for h in getattr(self, "glut", []) if not h.dead and not h.routed]
                if not left and self.timer > 3:
                    p.ehre += 60
                    self.complete(["Otto's army breaks. The Markgraf himself is taken prisoner.",
                                   "Heiligenstein stands — and with it, the Bishop's [Stimme|vote]."])

    def draw_objective(self, surf):
        st = self.cur
        if st is None or not st.get("text"):
            return
        c = CHAPTERS[min(self.ch, len(CHAPTERS) - 1)]
        r = panel(surf, (SCREEN_W - 420, 92, 410, 74), 175)
        text(surf, c["title"], (r.x + 10, r.y + 6), 13, GOLD)
        bilingual(surf, st["text"], (r.x + 10, r.y + 24), 13, 390, gloss=False)
        st_k = st["kind"]
        p = self.s.player
        if st_k in ("collect", "deliver"):
            text(surf, f"{p.inv.count(st['item'])}/{st['n']}", (r.right - 10, r.y + 6), 13, right=True)
        elif st_k == "money":
            text(surf, f"{p.inv.money}/{st['n']} Pf", (r.right - 10, r.y + 6), 13, right=True)
        # arrow toward the target
        tgt = None
        if st.get("tag") in self.npcs:
            h = self.npcs[st["tag"]]
            tgt = h.cx
        elif st.get("place"):
            tgt = self.sx(st["place"])
        if tgt is not None:
            d = tgt - p.cx
            if abs(d) > 500:
                arrow = "→" if d > 0 else "←"
                text(surf, f"{arrow} {abs(d) / TILE * 16 / 1000 * 0.4:.1f} Meilen", (r.right - 10, r.bottom - 18),
                     12, (220, 210, 170), right=True)
