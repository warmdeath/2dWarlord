"""Tiny procedural sound bank (numpy-synthesised), so the game ships without any asset files."""
import random

import numpy as np
import pygame

RATE = 22050


def _env(n, attack=0.005, decay=None):
    t = np.arange(n) / RATE
    a = np.clip(t / attack, 0, 1)
    d = np.exp(-t / (decay or (n / RATE / 4)))
    return a * d


def _noise(dur, decay, lp=0.0):
    n = int(RATE * dur)
    x = np.random.uniform(-1, 1, n)
    if lp > 0:
        for i in range(1, n):
            x[i] = x[i - 1] * lp + x[i] * (1 - lp)
    return x * _env(n, 0.002, decay)


def _tone(freq, dur, decay, harmonics=(1.0,), detune=0.0):
    n = int(RATE * dur)
    t = np.arange(n) / RATE
    x = np.zeros(n)
    for i, a in enumerate(harmonics):
        x += a * np.sin(2 * np.pi * freq * (i + 1) * t * (1 + detune * i))
    return x * _env(n, 0.002, decay)


def _sweep(f0, f1, dur, decay):
    n = int(RATE * dur)
    t = np.arange(n) / RATE
    f = np.linspace(f0, f1, n)
    return np.sin(2 * np.pi * np.cumsum(f) / RATE) * _env(n, 0.003, decay)


class Audio:
    def __init__(self):
        self.ok = False
        self.sounds = {}
        self.cool = {}
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(RATE, -16, 1, 512)
            self.ok = pygame.mixer.get_init() is not None
        except Exception:
            self.ok = False
        if self.ok:
            try:
                self._build()
            except Exception:
                self.ok = False

    def _mk(self, x, vol=0.5):
        x = np.clip(x / (np.max(np.abs(x)) + 1e-6) * vol, -1, 1)
        arr = (x * 32000).astype(np.int16)
        ch = pygame.mixer.get_init()[2]
        if ch == 2:
            arr = np.column_stack([arr, arr])
        return pygame.sndarray.make_sound(arr.copy())

    def _build(self):
        S = self.sounds
        S["hit"] = self._mk(_noise(0.12, 0.03, 0.6) + _tone(120, 0.12, 0.04) * 0.6, 0.45)
        S["block"] = self._mk(_tone(820, 0.18, 0.05, (1, 0.5, 0.3), 0.01) + _noise(0.05, 0.01) * 0.3, 0.35)
        S["parry"] = self._mk(_tone(1320, 0.35, 0.12, (1, 0.6, 0.4, 0.2), 0.003), 0.4)
        S["swing"] = self._mk(_noise(0.16, 0.06, 0.85), 0.18)
        S["dig"] = self._mk(_noise(0.08, 0.02, 0.5), 0.2)
        S["place"] = self._mk(_tone(180, 0.08, 0.02) + _noise(0.05, 0.01, 0.7) * 0.4, 0.25)
        S["tree"] = self._mk(_noise(0.6, 0.25, 0.92) + _tone(70, 0.6, 0.2) * 0.5, 0.45)
        S["bow"] = self._mk(_sweep(300, 120, 0.12, 0.05), 0.3)
        S["crossbow"] = self._mk(_tone(160, 0.1, 0.02) + _noise(0.1, 0.03, 0.4), 0.35)
        S["volley"] = self._mk(_noise(0.7, 0.3, 0.8), 0.3)
        S["impact"] = self._mk(_noise(0.5, 0.2, 0.9) + _tone(55, 0.5, 0.2), 0.6)
        S["thunder"] = self._mk(_noise(2.0, 0.7, 0.97), 0.7)
        S["collapse"] = self._mk(_noise(1.0, 0.4, 0.95), 0.55)
        S["door"] = self._mk(_sweep(140, 90, 0.2, 0.08), 0.2)
        S["gate"] = self._mk(_sweep(80, 50, 0.6, 0.25) + _noise(0.6, 0.3, 0.9) * 0.4, 0.35)
        S["anvil"] = self._mk(_tone(1760, 0.3, 0.08, (1, 0.4, 0.25), 0.002), 0.12)
        S["eat"] = self._mk(_noise(0.15, 0.04, 0.6), 0.15)
        S["hiss"] = self._mk(_noise(0.5, 0.2, 0.2), 0.2)
        S["bell"] = self._mk(_tone(392, 2.5, 0.9, (1, 0.5, 0.33, 0.2), 0.004), 0.35)
        S["horn"] = self._mk(_tone(220, 1.2, 0.8, (1, 0.7, 0.5, 0.3)), 0.35)
        S["ui"] = self._mk(_tone(660, 0.06, 0.02), 0.15)
        S["coin"] = self._mk(_tone(1900, 0.15, 0.05, (1, 0.3)), 0.2)

    def play(self, name):
        if not self.ok:
            return
        s = self.sounds.get(name)
        if s is None:
            return
        t = pygame.time.get_ticks()
        if t - self.cool.get(name, -999) < 45:
            return
        self.cool[name] = t
        try:
            s.set_volume(random.uniform(0.75, 1.0))
            s.play()
        except Exception:
            pass
