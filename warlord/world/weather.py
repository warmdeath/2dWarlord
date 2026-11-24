"""Time of day, seasons, wind and weather. The environment drives sailing, archery, fire, crops and mood."""
import math
import random

from ..settings import DAY_LENGTH, DAYS_PER_SEASON, SEASONS

WEATHER = {
    #  key        de          en         rain  cloud gloom  wind
    "klar": ("Klar", "clear", 0.0, 0.15, 0.0, 0.3),
    "wolkig": ("Bewölkt", "cloudy", 0.0, 0.6, 0.25, 0.5),
    "regen": ("Regen", "rain", 0.6, 0.85, 0.5, 0.6),
    "sturm": ("Sturm", "storm", 1.0, 1.0, 0.75, 1.0),
    "nebel": ("Nebel", "fog", 0.0, 0.5, 0.35, 0.1),
    "schnee": ("Schnee", "snow", 0.5, 0.8, 0.4, 0.4),
}

TRANSITIONS = {
    "klar": [("klar", 5), ("wolkig", 3), ("nebel", 1)],
    "wolkig": [("klar", 3), ("wolkig", 2), ("regen", 3), ("nebel", 1)],
    "regen": [("wolkig", 3), ("regen", 2), ("sturm", 1)],
    "sturm": [("regen", 3), ("wolkig", 1)],
    "nebel": [("klar", 2), ("wolkig", 2)],
    "schnee": [("wolkig", 2), ("schnee", 2), ("klar", 1)],
}


class Environment:
    def __init__(self, seed=0):
        self.rng = random.Random(seed)
        self.time = DAY_LENGTH * 0.30   # start in the morning
        self.weather = "klar"
        self.next_weather = "klar"
        self.blend = 1.0                # 0..1 transition into next_weather
        self.weather_timer = 160.0
        self.wind = 0.4                 # -1..1, + blows east
        self.wind_target = 0.4
        self.lightning = 0.0
        self.dt_hint = 0.016
        self.biome_hint = "plains"
        self.cold = False               # local climate (snowland / winter)
        self.forced = None

    # ---------------------------------------------------------------- clock
    @property
    def day(self):
        return int(self.time // DAY_LENGTH)

    def day_fraction(self):
        return (self.time % DAY_LENGTH) / DAY_LENGTH

    def season(self):
        return (self.day // DAYS_PER_SEASON) % 4

    def season_name(self):
        return SEASONS[self.season()]

    def hour(self):
        return self.day_fraction() * 24.0

    def clock_text(self):
        h = self.hour()
        return f"{int(h):02d}:{int((h % 1) * 60):02d}"

    def sun_height(self):
        # 06:00 sunrise, 18:00 sunset
        return math.sin((self.day_fraction() - 0.25) * math.tau)

    def is_night(self):
        return self.sun_height() < -0.05

    def daylight(self):
        s = self.sun_height()
        d = max(0.0, min(1.0, (s + 0.15) / 0.45))
        base = 0.42 + 0.58 * d
        return base * (1.0 - 0.35 * self.gloom())

    def ambient_color(self):
        s = self.sun_height()
        if s > 0.3:
            c = (255, 252, 244)
        elif s > 0.0:
            t = s / 0.3
            c = (255, int(200 + 52 * t), int(170 + 74 * t))
        else:
            t = min(1.0, -s / 0.3)
            c = (int(255 - 125 * t), int(200 - 55 * t), int(170 + 50 * t))
        g = self.gloom()
        return tuple(int(v * (1 - 0.15 * g)) for v in c)

    # ---------------------------------------------------------------- weather values
    def _val(self, idx):
        a = WEATHER[self.weather][idx]
        b = WEATHER[self.next_weather][idx]
        return a + (b - a) * self.blend

    def rain(self):
        return self._val(2)

    def cloud_cover(self):
        return self._val(3)

    def gloom(self):
        return self._val(4)

    def is_snowing(self):
        w = self.next_weather if self.blend > 0.5 else self.weather
        return w == "schnee" or (self.cold and self.rain() > 0.2)

    def is_raining(self):
        return self.rain() > 0.25 and not self.is_snowing()

    def fog(self):
        a = 1.0 if self.weather == "nebel" else 0.0
        b = 1.0 if self.next_weather == "nebel" else 0.0
        return 0.55 * (a + (b - a) * self.blend)

    def current(self):
        k = self.next_weather if self.blend > 0.5 else self.weather
        return k, WEATHER[k][0], WEATHER[k][1]

    def force(self, key):
        self.weather = self.next_weather = key
        self.blend = 1.0
        self.weather_timer = 200

    # ---------------------------------------------------------------- update
    def update(self, dt, biome):
        self.dt_hint = dt
        self.time += dt
        self.biome_hint = biome
        self.cold = biome in ("snow",) or self.season() == 3
        if self.blend < 1.0:
            self.blend = min(1.0, self.blend + dt / 25.0)
            if self.blend >= 1.0:
                self.weather = self.next_weather
        self.weather_timer -= dt
        if self.weather_timer <= 0 and self.blend >= 1.0:
            opts = TRANSITIONS[self.weather]
            choice = self.rng.choices([o[0] for o in opts], [o[1] for o in opts])[0]
            if self.cold and choice in ("regen", "sturm"):
                choice = "schnee"
            if not self.cold and choice == "schnee":
                choice = "regen"
            self.next_weather = choice
            self.blend = 0.0 if choice != self.weather else 1.0
            self.weather_timer = self.rng.uniform(120, 300)
            self.wind_target = self.rng.uniform(-1, 1) * WEATHER[choice][5] + self.rng.uniform(-0.2, 0.2)
        # gusts
        if self.rng.random() < dt * 0.05:
            self.wind_target += self.rng.uniform(-0.3, 0.3)
        lim = 0.25 + self._val(5)
        self.wind_target = max(-lim, min(lim, self.wind_target))
        if biome == "edge" or biome == "abyss":
            self.wind_target = min(self.wind_target, -0.5)  # the abyss inhales
        if biome in ("volcanic", "lavasea"):
            self.wind_target = max(self.wind_target, 0.4)
        self.wind += (self.wind_target - self.wind) * min(1.0, dt * 0.3)
        # lightning
        self.lightning = max(0.0, self.lightning - dt * 3)
        w = self.next_weather if self.blend > 0.5 else self.weather
        if w == "sturm" and self.rng.random() < dt * 0.12:
            self.lightning = 1.0
            return "lightning"
        return None

    def wind_text(self):
        s = abs(self.wind)
        d = "Ost" if self.wind > 0 else "West"
        label = "Flaute" if s < 0.12 else "Brise" if s < 0.45 else "Wind" if s < 0.8 else "Sturmwind"
        gloss = {"Flaute": "calm", "Brise": "breeze", "Wind": "wind", "Sturmwind": "gale"}[label]
        arrow = "→" if self.wind > 0 else "←"
        return f"{label} {arrow} ({gloss}, nach {d})"
