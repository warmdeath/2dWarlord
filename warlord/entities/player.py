"""The player: a Humanoid plus inventory, honour, social rank, fiefs, retinue and dictionary."""
from ..items.inventory import Inventory
from ..society.dialogue import Woerterbuch
from ..society.names import make_look
from .humanoid import Humanoid


class Player(Humanoid):
    def __init__(self, x, y, rng, name="Konrad", rank=0):
        look = make_look(rng, rank, "farmer")
        look["hat"] = "gugel"
        look["hat_color"] = (120, 70, 40)
        look["tunic"] = (104, 120, 84)
        look["beard"] = False
        super().__init__(x, y, look, "player", name, rank)
        self.inv = Inventory()
        self.ehre = 0            # honour
        self.liege = None        # kingdom key you serve
        self.lord_name = None
        self.fiefs = []          # settlement indices you hold
        self.followers = []
        self.haufen = []
        self.dict = Woerterbuch()
        self.hunger = 100.0
        self.max_hp = 100
        self.hp = 100
        self.skill = 0.8
        self.selected_haufen = -1
        self.citizen_of = None
        self.days_in_city = 0
        self.knight_master = None
        self.boat = None
        self.skyfall = False
        self.stats = {"kills": 0, "battles": 0, "words": 0, "crafted": 0, "built": 0}
        self.free = rank >= 1
        self.title = ""

    def update_look_for_rank(self, colors=None):
        r = self.rank
        if r >= 2:
            self.look["tunic"] = (56, 80, 140) if r == 2 else (150, 24, 36)
            self.look["hat"] = "cap" if r == 2 else None
        if r >= 4 and colors:
            self.look["tabard"] = colors
        if r >= 5:
            self.look["trim"] = (214, 178, 74)
            self.look["hat"] = "coronet"
