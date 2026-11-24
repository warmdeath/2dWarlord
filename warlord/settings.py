"""Global constants. Everything tunable lives here so systems stay data-driven."""

SCREEN_W, SCREEN_H = 1280, 720
FPS = 60
TITLE = "WARLORD — Anno 1300"

TILE = 16                 # pixels per tile
CHUNK = 32                # tiles per render chunk edge

# World size. 48 000 tiles * 16 px / 215 px/s (horse gallop) ~= 59.5 minutes end to end.
WORLD_SIZES = {
    "klein": 12000,       # small  (~15 min ride)
    "mittel": 24000,      # medium (~30 min ride)
    "gross": 48000,       # large  (~1 hour ride) — the "real" world
}
WORLD_H = 256
SEA_LEVEL = 112           # tile row of the ocean surface
BEDROCK_ROWS = 3

# Physics (pixels, seconds)
GRAVITY = 1500.0
MAX_FALL = 900.0
WALK_SPEED = 80.0
RUN_SPEED = 150.0
CROUCH_SPEED = 40.0
SWIM_SPEED = 60.0
JUMP_SPEED = 470.0
HORSE_WALK = 110.0
HORSE_GALLOP = 215.0
CLIMB_SPEED = 90.0

DAY_LENGTH = 600.0        # seconds of real time per in-game day
DAYS_PER_SEASON = 4
SEASONS = [("Frühling", "spring"), ("Sommer", "summer"), ("Herbst", "autumn"), ("Winter", "winter")]

# Palette — muted, painterly medieval tones
INK = (24, 20, 18)
PARCHMENT = (226, 210, 172)
PARCHMENT_DARK = (186, 164, 120)
GOLD = (214, 178, 74)
BLOOD = (150, 34, 30)
WHITE = (240, 236, 226)
GREY = (120, 118, 112)
DARK = (34, 30, 30)
GERMAN_COLOR = (240, 196, 92)   # highlight colour for German words
GLOSS_COLOR = (170, 190, 205)

FACTION_PLAYER = "player"
