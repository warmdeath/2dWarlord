"""Application shell: window, main loop, scene switching, save/load."""
import os
import pickle
import sys
import zlib

import pygame

from ..settings import SCREEN_W, SCREEN_H, FPS, TITLE, WORLD_SIZES
from ..ui.menu import Menu, Loading
from .. import audio

SAVE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "saves")
SAVE_FILE = os.path.join(SAVE_DIR, "spielstand.sav")


class App:
    def __init__(self, headless=False):
        pygame.init()
        pygame.display.set_caption(TITLE)
        flags = pygame.SCALED | pygame.RESIZABLE if not headless else 0
        try:
            self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), flags, vsync=1)
        except Exception:
            self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        self.clock = pygame.time.Clock()
        self.audio = audio.Audio()
        self.scene = Menu(self)
        self.session = None
        self.running = True
        self.show_fps = False

    # ------------------------------------------------------------------ scenes
    def to_menu(self):
        self.session = None
        self.scene = Menu(self)

    def start_sandbox(self, size="gross", seed=1300):
        from ..world.generator import generate
        from ..modes.session import Session
        out = {}

        def done():
            s = Session(self, out["world"], mode="sandbox", seed=seed, player_rank=1)
            s.give_start_kit("sandbox")
            s.ui.show_card("Der Sandkasten", [
                "You are a [freier Bauer|free peasant] with a sword, a bow and some planks.",
                "Seven realms lie between the [Abgrund|abyss] and the [Glutmeer|fire sea].",
                "Trade, build, fight robbers, swear [Treue|loyalty] to a lord, rise from [Bauer|peasant] to "
                "[Graf|count] — or ride the hour from one end of the world to the other.",
                "", "H = help at any time."], subtitle="(the sandbox)")
            self.session = s
            self.scene = PlayScene(self, s)

        self.scene = Loading(self, generate(WORLD_SIZES[size], seed, out), done)

    def start_story(self):
        from ..world.generator import generate
        from ..modes.session import Session
        from ..modes.story import Story
        out = {}

        def done():
            s = Session(self, out["world"], mode="story", seed=1300, player_rank=0)
            s.give_start_kit("story")
            s.story = Story(s)
            s.story.begin()
            self.session = s
            self.scene = PlayScene(self, s)

        self.scene = Loading(self, generate(WORLD_SIZES["gross"], 1300, out), done, "Die Chronik beginnt")

    def start_battle(self, key):
        from ..modes.battle import build_battle
        s = build_battle(self, key)
        self.session = s
        self.scene = PlayScene(self, s)

    # ------------------------------------------------------------------ persistence
    def has_save(self):
        return os.path.exists(SAVE_FILE)

    def save_game(self):
        if self.session is None:
            return
        os.makedirs(SAVE_DIR, exist_ok=True)
        data = zlib.compress(pickle.dumps(self.session, protocol=pickle.HIGHEST_PROTOCOL), 1)
        tmp = SAVE_FILE + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, SAVE_FILE)

    def load_game(self):
        if not self.has_save():
            return
        with open(SAVE_FILE, "rb") as f:
            s = pickle.loads(zlib.decompress(f.read()))
        s.restore(self)
        self.session = s
        self.scene = PlayScene(self, s)
        s.ui.toast("[Geladen|loaded].")

    # ------------------------------------------------------------------ loop
    def run(self):
        while self.running:
            dt = min(0.05, self.clock.tick(FPS) / 1000.0)
            events = pygame.event.get()
            for e in events:
                if e.type == pygame.QUIT:
                    self.running = False
                elif e.type == pygame.KEYDOWN and e.key == pygame.K_F3:
                    self.show_fps = not self.show_fps
                elif e.type == pygame.KEYDOWN and e.key == pygame.K_F11:
                    pygame.display.toggle_fullscreen()
            self.scene.update(dt, events)
            self.scene.draw(self.screen)
            if self.show_fps:
                from ..ui.common import text
                text(self.screen, f"{self.clock.get_fps():.0f} fps", (SCREEN_W - 70, SCREEN_H - 40), 12)
            pygame.display.flip()
        pygame.quit()


class PlayScene:
    def __init__(self, app, session):
        self.app = app
        self.s = session

    def update(self, dt, events):
        keys = pygame.key.get_pressed()
        mb = pygame.mouse.get_pressed()
        self.s.update(dt, events, keys, mb, pygame.mouse.get_pos())

    def draw(self, surf):
        self.s.draw(surf)


def main():
    App().run()
