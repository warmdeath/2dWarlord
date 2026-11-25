"""Main menu: a quiet dusk scene with a castle on a hill. Every option in German with English beneath."""
import math
import os
import random

import pygame

from ..settings import SCREEN_W, SCREEN_H, GOLD
from .common import font, text, panel


class Menu:
    def __init__(self, app):
        self.app = app
        self.t = 0.0
        self.sel = 0
        self.page = "main"
        self.size = 2
        self.seed = random.randint(1, 99999)
        self.clouds = [[random.uniform(0, SCREEN_W), random.uniform(40, 260), random.uniform(60, 160)]
                       for _ in range(7)]
        self.stars = [(random.uniform(0, SCREEN_W), random.uniform(0, SCREEN_H * 0.5), random.random())
                      for _ in range(90)]
        self.rects = []

    def items(self):
        if self.page == "main":
            out = [("Geschichte", "Story — the chronicle of Konrad, serf of Erlenbach", "story"),
                   ("Sandkasten", "Sandbox — the open world of the seven realms", "sandbox"),
                   ("Feldschlacht", "Field battle — command formations in a set-piece battle", "battle")]
            if self.app.has_save():
                out.insert(0, ("Fortsetzen", "Continue your saved game", "continue"))
            out.append(("Beenden", "Quit", "quit"))
            return out
        if self.page == "sandbox":
            sizes = [("Klein", "small — 15 min ride"), ("Mittel", "medium — 30 min ride"),
                     ("Groß", "large — one hour's ride, end to end")]
            de, en = sizes[self.size]
            return [(f"Weltgröße: {de}", en + "  (←/→ or click)", "size"),
                    (f"Saat: {self.seed}", "seed — click for a new world", "seed"),
                    ("Los!", "Begin as a free peasant", "go_sandbox"),
                    ("Zurück", "back", "back")]
        if self.page == "battle":
            return [("Die Furt", "The Ford — hold the river crossing against a larger host", "b_ford"),
                    ("Die Klause", "The Pass — a gate in the mountains, a few against many", "b_pass"),
                    ("Offene Feldschlacht", "Open field — knights, pikes and bows", "b_field"),
                    ("Die Belagerung", "The Siege — moat, ram, trebuchet, ladders, sappers", "b_siege"),
                    ("Die Verteidigung", "The Defence — hold your castle against Otto's thunder-guns",
                     "b_verteidigung"),
                    ("Zurück", "back", "back")]
        return []

    def update(self, dt, events):
        self.t += dt
        its = self.items()
        for e in events:
            if e.type == pygame.KEYDOWN:
                if e.key in (pygame.K_UP, pygame.K_w):
                    self.sel = (self.sel - 1) % len(its)
                    self.app.audio.play("ui")
                elif e.key in (pygame.K_DOWN, pygame.K_s):
                    self.sel = (self.sel + 1) % len(its)
                    self.app.audio.play("ui")
                elif e.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.choose(its[self.sel][2])
                elif e.key in (pygame.K_LEFT, pygame.K_RIGHT) and self.page == "sandbox" and its[self.sel][2] == "size":
                    self.size = (self.size + (1 if e.key == pygame.K_RIGHT else -1)) % 3
                elif e.key == pygame.K_ESCAPE:
                    if self.page != "main":
                        self.page = "main"
                        self.sel = 0
            elif e.type == pygame.MOUSEMOTION:
                for i, r in enumerate(self.rects):
                    if r.collidepoint(e.pos):
                        self.sel = i
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                for i, r in enumerate(self.rects):
                    if r.collidepoint(e.pos):
                        self.sel = i
                        self.choose(its[i][2])

    def choose(self, key):
        a = self.app
        a.audio.play("ui")
        if key == "story":
            a.start_story()
        elif key == "sandbox":
            self.page = "sandbox"
            self.sel = 2
        elif key == "battle":
            self.page = "battle"
            self.sel = 0
        elif key == "continue":
            a.load_game()
        elif key == "quit":
            a.running = False
        elif key == "size":
            self.size = (self.size + 1) % 3
        elif key == "seed":
            self.seed = random.randint(1, 99999)
        elif key == "go_sandbox":
            a.start_sandbox(["klein", "mittel", "gross"][self.size], self.seed)
        elif key == "back":
            self.page = "main"
            self.sel = 0
        elif key.startswith("b_"):
            a.start_battle(key[2:])

    # ------------------------------------------------------------------ drawing
    def draw(self, surf):
        t = self.t
        # dusk sky
        for i in range(0, SCREEN_H, 4):
            f = i / SCREEN_H
            c = (int(20 + 150 * f ** 2.2), int(18 + 70 * f ** 2.0), int(46 + 40 * f))
            surf.fill(c, (0, i, SCREEN_W, 4))
        for x, y, tw in self.stars:
            b = int(120 + 100 * math.sin(t * 1.5 + tw * 9))
            if y < SCREEN_H * 0.4:
                surf.set_at((int(x), int(y)), (b, b, min(255, b + 30)))
        pygame.draw.circle(surf, (250, 220, 170), (int(SCREEN_W * 0.78), 170), 46)
        pygame.draw.circle(surf, (255, 236, 200), (int(SCREEN_W * 0.78), 170), 38)
        for c in self.clouds:
            c[0] = (c[0] + 8 * (1 / 60)) % (SCREEN_W + 300)
            x = c[0] - 150
            for k in range(3):
                pygame.draw.ellipse(surf, (120, 80, 90), (x + k * c[2] * 0.35, c[1] + (k % 2) * 8, c[2], c[2] * 0.3))
        # far mountains
        pts = [(0, SCREEN_H)]
        for x in range(0, SCREEN_W + 20, 20):
            h = 380 + math.sin(x * 0.006) * 50 + math.sin(x * 0.017 + 1) * 25 + abs(math.sin(x * 0.03)) * -30
            pts.append((x, h))
        pts.append((SCREEN_W, SCREEN_H))
        pygame.draw.polygon(surf, (70, 50, 70), pts)
        # hill with castle
        pts = [(0, SCREEN_H)]
        for x in range(0, SCREEN_W + 20, 16):
            h = 520 - 120 * math.exp(-((x - 930) / 260) ** 2) + math.sin(x * 0.01) * 10
            pts.append((x, h))
        pts.append((SCREEN_W, SCREEN_H))
        hill = (36, 28, 40)
        pygame.draw.polygon(surf, hill, pts)
        cx, cy = 930, 402
        for dx, w, h in ((-110, 26, 90), (-60, 120, 50), (-20, 34, 130), (60, 26, 80), (90, 60, 40)):
            pygame.draw.rect(surf, hill, (cx + dx, cy - h, w, h + 10))
            for k in range(w // 8 + 1):
                pygame.draw.rect(surf, hill, (cx + dx + k * 8, cy - h - 6, 4, 6))
        pygame.draw.polygon(surf, hill, [(cx - 24, cy - 130), (cx - 3, cy - 172), (cx + 18, cy - 130)])
        flutter = math.sin(t * 4) * 3
        pygame.draw.line(surf, hill, (cx - 3, cy - 172), (cx - 3, cy - 196), 2)
        pygame.draw.polygon(surf, (150, 30, 30), [(cx - 3, cy - 196), (cx + 22, cy - 190 + flutter), (cx - 3, cy - 184)])
        for k in range(6):
            wx = cx - 40 + k * 14
            if int(t * 0.7 + k) % 3:
                pygame.draw.rect(surf, (255, 190, 90), (wx, cy - 40 + (k % 2) * 14, 3, 5))
        # near trees
        pts = [(0, SCREEN_H)]
        for x in range(0, SCREEN_W + 24, 24):
            h = 640 + math.sin(x * 0.02) * 12
            pts.append((x, h))
        pts.append((SCREEN_W, SCREEN_H))
        pygame.draw.polygon(surf, (16, 14, 20), pts)
        for x in range(10, SCREEN_W, 38):
            hh = 60 + (x * 7919) % 50
            pygame.draw.polygon(surf, (16, 14, 20), [(x - 14, 650), (x, 650 - hh), (x + 14, 650)])
        # title
        title = font(84, bold=True).render("WARLORD", True, (236, 210, 150))
        sh = font(84, bold=True).render("WARLORD", True, (0, 0, 0))
        surf.blit(sh, (84, 64))
        surf.blit(title, (80, 60))
        text(surf, "Anno Domini 1300", (86, 150), 26, (220, 190, 140))
        text(surf, "Sieben Reiche zwischen Abgrund und Glut  ·  seven realms between the abyss and the fire",
             (86, 186), 14, (190, 170, 150))
        # options
        its = self.items()
        self.rects = []
        y = 260
        for i, (de, en, key) in enumerate(its):
            r = pygame.Rect(80, y, 520, 56)
            sel = i == self.sel
            if sel:
                panel(surf, r, 150, border=GOLD)
                pygame.draw.polygon(surf, GOLD, [(r.x - 16, r.y + 20), (r.x - 6, r.y + 28), (r.x - 16, r.y + 36)])
            text(surf, de, (r.x + 16, r.y + 5), 26, GOLD if sel else (230, 220, 200), bold=sel)
            text(surf, en, (r.x + 18, r.y + 36), 13, (200, 190, 170) if sel else (150, 140, 130))
            self.rects.append(r)
            y += 64
        text(surf, "↑↓ + Enter · Maus (mouse)", (86, SCREEN_H - 30), 12, (150, 140, 130))
        text(surf, "v2 — the chronicle rewritten", (SCREEN_W - 16, SCREEN_H - 30), 12, (150, 140, 130), right=True)


class Loading:
    def __init__(self, app, gen, on_done, title="Die Welt entsteht"):
        self.app = app
        self.gen = gen
        self.on_done = on_done
        self.p = 0.0
        self.label = ""
        self.title = title
        self.done = False

    def update(self, dt, events):
        if self.done:
            return
        try:
            self.p, self.label = next(self.gen)
        except StopIteration:
            self.done = True
            self.on_done()

    def draw(self, surf):
        surf.fill((18, 16, 20))
        text(surf, self.title, (SCREEN_W // 2, SCREEN_H // 2 - 80), 36, GOLD, center=True, bold=True)
        text(surf, "(the world is being made)", (SCREEN_W // 2, SCREEN_H // 2 - 36), 15, (190, 180, 160), center=True)
        r = pygame.Rect(SCREEN_W // 2 - 300, SCREEN_H // 2, 600, 16)
        pygame.draw.rect(surf, (50, 44, 40), r, border_radius=6)
        pygame.draw.rect(surf, GOLD, (r.x, r.y, int(r.w * self.p), r.h), border_radius=6)
        text(surf, self.label, (SCREEN_W // 2, SCREEN_H // 2 + 30), 15, (210, 200, 180), center=True)
