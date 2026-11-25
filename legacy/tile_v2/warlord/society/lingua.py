"""Die Sprachschule — progressive German ("diglot weave").

Every English sentence the game shows (UI labels, item names, NPC speech, toasts, chronicle
pages) is passed through this engine. Words you are *learning* are swapped for their German
form with the English gloss beside them; words you have *mastered* appear in German alone.

    stage 0  unknown   -> English
    stage 1  learning  -> Deutsch (english)
    stage 2  mastered  -> Deutsch                   (seen >= 10 times, in >= 2 separate sessions)

At the start about a fifth of the vocabulary — the most important words — is in the learning
set. Each time a word is mastered, a new one is introduced, so the game slowly drifts from
English into German as you play. Progress lives in a profile file and survives across saves.
"""
import json
import os
import re
import time

from .dialogue import TOKEN

MASTER_COUNT = 10
MASTER_SESSIONS = 2

# (english, deutsch, tier)  tier 1 = first 20%, introduced from the start
VOCAB = [
    # ---- tier 1: core words you see constantly
    ("good morning", "Guten Morgen", 1), ("good day", "Guten Tag", 1), ("good evening", "Guten Abend", 1),
    ("good night", "Gute Nacht", 1), ("goodbye", "Auf Wiedersehen", 1),
    ("breath", "Atem", 1), ("breeze", "Brise", 2), ("calm", "Flaute", 3), ("gale", "Sturmwind", 3),
    ("east", "Osten", 2), ("west", "Westen", 2), ("resume", "weiter", 2), ("main menu", "Hauptmenü", 3),
    ("blueprints", "Baupläne", 2), ("crafting", "Handwerk", 2), ("trade", "Handel", 1), ("pennies", "Pfennig", 1),
    ("life", "Leben", 1), ("health", "Gesundheit", 1), ("stamina", "Ausdauer", 1), ("hunger", "Hunger", 1),
    ("day", "Tag", 1), ("night", "Nacht", 1), ("morning", "Morgen", 1), ("evening", "Abend", 1),
    ("yes", "ja", 1), ("no", "nein", 1), ("and", "und", 1), ("the king", "der König", 1),
    ("king", "König", 1), ("knight", "Ritter", 1), ("lord", "Herr", 1), ("castle", "Burg", 1),
    ("village", "Dorf", 1), ("town", "Stadt", 1), ("city", "Stadt", 1), ("house", "Haus", 1),
    ("bread", "Brot", 1), ("water", "Wasser", 1), ("fire", "Feuer", 1), ("sword", "Schwert", 1),
    ("shield", "Schild", 1), ("horse", "Pferd", 1), ("money", "Geld", 1), ("honour", "Ehre", 1),
    ("help", "Hilfe", 1), ("map", "Karte", 1), ("inventory", "Inventar", 1), ("orders", "Befehle", 1),
    ("wind", "Wind", 1), ("rain", "Regen", 1), ("sun", "Sonne", 1), ("wood", "Holz", 1), ("stone", "Stein", 1),
    ("gate", "Tor", 1), ("wall", "Mauer", 1), ("war", "Krieg", 1), ("peace", "Frieden", 1),
    ("good", "gut", 1), ("thank you", "danke", 1), ("please", "bitte", 1), ("friend", "Freund", 1),
    ("enemy", "Feind", 1), ("enemies", "Feinde", 1), ("man", "Mann", 1), ("men", "Männer", 1),
    ("woman", "Frau", 1), ("child", "Kind", 1), ("God", "Gott", 1), ("church", "Kirche", 1),
    ("field", "Feld", 1), ("wheat", "Weizen", 1),
    # ---- tier 2: common
    ("today", "heute", 2), ("tomorrow", "morgen", 2), ("now", "jetzt", 2), ("here", "hier", 2),
    ("there", "dort", 2), ("big", "groß", 2), ("small", "klein", 2), ("old", "alt", 2), ("new", "neu", 2),
    ("fresh", "frisch", 2), ("hot", "heiß", 2), ("cold", "kalt", 2), ("dark", "dunkel", 2),
    ("light", "Licht", 2), ("road", "Weg", 2), ("forest", "Wald", 2), ("mountain", "Berg", 2),
    ("mountains", "Berge", 2), ("sea", "Meer", 2), ("ship", "Schiff", 2), ("boat", "Boot", 2),
    ("river", "Fluss", 2), ("bridge", "Brücke", 2), ("tower", "Turm", 2), ("market", "Markt", 2),
    ("price", "Preis", 2), ("buy", "kaufen", 2), ("sell", "verkaufen", 2), ("work", "Arbeit", 2),
    ("food", "Essen", 2), ("meat", "Fleisch", 2), ("fish", "Fisch", 2), ("beer", "Bier", 2), ("wine", "Wein", 2),
    ("salt", "Salz", 2), ("iron", "Eisen", 2), ("silver", "Silber", 2), ("gold", "Gold", 2),
    ("cloth", "Tuch", 2), ("wool", "Wolle", 2), ("sheep", "Schafe", 2), ("cow", "Kuh", 2),
    ("pig", "Schwein", 2), ("dog", "Hund", 2), ("wolf", "Wolf", 2), ("wolves", "Wölfe", 2),
    ("tree", "Baum", 2), ("trees", "Bäume", 2), ("flower", "Blume", 2), ("grass", "Gras", 2),
    ("snow", "Schnee", 2), ("storm", "Sturm", 2), ("fog", "Nebel", 2), ("clear", "klar", 2),
    ("cloudy", "bewölkt", 2), ("spring", "Frühling", 2), ("summer", "Sommer", 2), ("autumn", "Herbst", 2),
    ("winter", "Winter", 2), ("year", "Jahr", 2), ("time", "Zeit", 2), ("hour", "Stunde", 2),
    ("bow", "Bogen", 2), ("arrow", "Pfeil", 2), ("arrows", "Pfeile", 2), ("spear", "Speer", 2),
    ("axe", "Axt", 2), ("helmet", "Helm", 2), ("armour", "Rüstung", 2), ("wound", "Wunde", 2),
    ("wounds", "Wunden", 2), ("blood", "Blut", 2), ("death", "Tod", 2), ("victory", "Sieg", 2),
    ("army", "Heer", 2), ("soldier", "Soldat", 2), ("soldiers", "Soldaten", 2), ("guard", "Wache", 2),
    ("attack", "Angriff", 2), ("forward", "vorwärts", 2), ("back", "zurück", 2), ("fief", "Lehen", 2),
    ("farmer", "Bauer", 2), ("peasant", "Bauer", 2), ("peasants", "Bauern", 2), ("smith", "Schmied", 2),
    ("merchant", "Händler", 2), ("priest", "Priester", 2), ("monk", "Mönch", 2), ("count", "Graf", 2),
    ("duke", "Herzog", 2), ("queen", "Königin", 2), ("emperor", "Kaiser", 2), ("crown", "Krone", 2),
    ("land", "Land", 2), ("world", "Welt", 2), ("edge", "Rand", 2), ("abyss", "Abgrund", 2),
    ("sky", "Himmel", 2), ("earth", "Erde", 2), ("door", "Tür", 2), ("bed", "Bett", 2), ("chest", "Truhe", 2),
    ("ladder", "Leiter", 2), ("moat", "Graben", 2), ("pitch", "Pech", 2), ("siege", "Belagerung", 2),
    ("save", "speichern", 2), ("saved", "gespeichert", 2), ("loaded", "geladen", 2), ("built", "gebaut", 2),
    ("words", "Wörter", 2), ("word", "Wort", 2), ("new", "neu", 2), ("quiz", "Quiz", 2),
    # ---- tier 3: richer
    ("always", "immer", 3), ("never", "nie", 3), ("very", "sehr", 3), ("too", "zu", 3), ("only", "nur", 3),
    ("again", "wieder", 3), ("soon", "bald", 3), ("still", "noch", 3), ("everything", "alles", 3),
    ("nothing", "nichts", 3), ("someone", "jemand", 3), ("nobody", "niemand", 3), ("why", "warum", 3),
    ("where", "wo", 3), ("what", "was", 3), ("who", "wer", 3), ("how", "wie", 3), ("when", "wenn", 3),
    ("with", "mit", 3), ("without", "ohne", 3), ("for", "für", 3), ("from", "von", 3), ("my", "mein", 3),
    ("your", "dein", 3), ("our", "unser", 3), ("we", "wir", 3), ("strong", "stark", 3), ("weak", "schwach", 3),
    ("rich", "reich", 3), ("poor", "arm", 3), ("free", "frei", 3), ("brother", "Bruder", 3),
    ("sister", "Schwester", 3), ("mother", "Mutter", 3), ("father", "Vater", 3), ("son", "Sohn", 3),
    ("sons", "Söhne", 3), ("harvest", "Ernte", 3), ("mill", "Mühle", 3), ("flour", "Mehl", 3),
    ("oven", "Ofen", 3), ("hammer", "Hammer", 3), ("anvil", "Amboss", 3), ("coal", "Kohle", 3),
    ("ore", "Erz", 3), ("cave", "Höhle", 3), ("tunnel", "Tunnel", 3), ("hill", "Hügel", 3),
    ("valley", "Tal", 3), ("island", "Insel", 3), ("coast", "Küste", 3), ("harbour", "Hafen", 3),
    ("sail", "Segel", 3), ("waves", "Wellen", 3), ("lightning", "Blitz", 3), ("thunder", "Donner", 3),
    ("trebuchet", "Blide", 3), ("ram", "Rammbock", 3), ("drawbridge", "Zugbrücke", 3),
    ("portcullis", "Fallgatter", 3), ("tithe", "Zehnt", 3), ("tax", "Steuer", 3), ("taxes", "Steuern", 3),
    ("law", "Gesetz", 3), ("thief", "Dieb", 3), ("crime", "Verbrechen", 3), ("court", "Hof", 3),
    ("oath", "Eid", 3), ("loyalty", "Treue", 3), ("battle", "Schlacht", 3), ("charge", "Ansturm", 3),
    ("archers", "Bogenschützen", 3), ("knights", "Ritter", 3), ("bandage", "Verband", 3),
    ("head", "Kopf", 3), ("arm", "Arm", 3), ("legs", "Beine", 3), ("hand", "Hand", 3),
]

_EN = {}
for _en, _de, _tier in VOCAB:
    _EN[_en.lower()] = (_de, _tier)
# longest phrases first so "thank you" wins over "you"
_PHRASES = sorted(_EN.keys(), key=lambda s: -len(s))
_RX = re.compile(r"\b(" + "|".join(re.escape(p) for p in _PHRASES) + r")\b", re.IGNORECASE)


def _profile_path():
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "saves")
    return os.path.join(base, "lexikon.json")


class Lingua:
    def __init__(self, path=None):
        self.path = path or _profile_path()
        self.words = {}          # de -> {"n": int, "s": [sessions], "en": str}
        self.session = 0
        self.learning = []       # ordered list of de words in the learning set
        self.last_ui_count = {}
        self.dirty = False
        self.enabled = True
        self.load()

    # ---------------------------------------------------------------- persistence
    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.words = d.get("words", {})
            self.session = d.get("session", 0)
            self.learning = d.get("learning", [])
        except (OSError, ValueError):
            pass
        if not self.learning:
            self.learning = [de for en, de, tier in VOCAB if tier == 1]
            self.learning = list(dict.fromkeys(self.learning))

    def save(self):
        if not self.dirty:
            return
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"session": self.session, "words": self.words, "learning": self.learning}, f,
                          ensure_ascii=False)
            os.replace(tmp, self.path)
            self.dirty = False
        except OSError:
            pass

    def new_session(self):
        self.session += 1
        self.dirty = True

    # ---------------------------------------------------------------- stages
    def stage(self, de):
        w = self.words.get(de)
        if w and w["n"] >= MASTER_COUNT and len(w["s"]) >= MASTER_SESSIONS:
            return 2
        if de in self.learning:
            return 1
        return 0

    def mastered(self):
        return [de for de in self.words if self.stage(de) == 2]

    def heard(self, de, en=""):
        w = self.words.get(de)
        if w is None:
            w = self.words[de] = {"n": 0, "s": [], "en": en}
        before = self.stage(de)
        w["n"] += 1
        if self.session not in w["s"]:
            w["s"].append(self.session)
            w["s"] = w["s"][-6:]
        self.dirty = True
        if before != 2 and self.stage(de) == 2:
            self._promote()
            return True
        return False

    def _promote(self):
        """A word was mastered: bring the next unknown word into the learning set."""
        active = [de for de in self.learning if self.stage(de) == 1]
        target = 12 + len(self.mastered()) // 3
        for en, de, tier in VOCAB:
            if len(active) >= target:
                break
            if de not in self.learning:
                self.learning.append(de)
                active.append(de)

    def progress(self):
        total = len({de for _, de, _ in VOCAB})
        return len([de for de in set(d for _, d, _ in VOCAB) if self.stage(de) == 2]), \
            len([de for de in set(d for _, d, _ in VOCAB) if self.stage(de) == 1]), total

    # ---------------------------------------------------------------- weaving
    def weave(self, text):
        """Return text with [de|en] tokens for learning words and [de|] for mastered ones."""
        if not self.enabled or not text:
            return text
        out = []
        pos = 0
        for m in TOKEN.finditer(text):
            out.append(self._weave_plain(text[pos:m.start()]))
            de, en = m.group(1), m.group(2)
            out.append(f"[{de}|]" if self.stage(de) == 2 else m.group(0))
            pos = m.end()
        out.append(self._weave_plain(text[pos:]))
        return "".join(out)

    def _weave_plain(self, s):
        if not s:
            return s

        def rep(m):
            en = m.group(0)
            de, tier = _EN[en.lower()]
            st = self.stage(de)
            if st == 0:
                return en
            if st == 1 and de.lower() != en.lower():
                return f"[{de}|{en.lower()}]"
            return f"[{de}|]"
        return _RX.sub(rep, s)

    def count_text(self, text, throttle=False):
        """Record every German word that appears in a displayed text."""
        now = time.time()
        newly = []
        for m in TOKEN.finditer(text):
            de, en = m.group(1), m.group(2)
            if throttle:
                if now - self.last_ui_count.get(de, 0) < 45:
                    continue
                self.last_ui_count[de] = now
            if self.heard(de, en):
                newly.append(de)
        return newly

    def term(self, en):
        """UI label: the woven form of an English term."""
        return self.weave(en)


_instance = None


def _extend_with_items():
    """Every item and tile name is vocabulary too (introduced after the core words)."""
    global _RX, _PHRASES
    from ..items.items import ITEMS
    added = False
    for d in ITEMS.values():
        en = d.en.lower()
        if en not in _EN and len(en) > 2:
            _EN[en] = (d.de, 3)
            VOCAB.append((en, d.de, 3))
            added = True
    if added:
        _PHRASES = sorted(_EN.keys(), key=lambda s: -len(s))
        _RX = re.compile(r"\b(" + "|".join(re.escape(p) for p in _PHRASES) + r")\b", re.IGNORECASE)


def get():
    global _instance
    if _instance is None:
        _extend_with_items()
        _instance = Lingua()
    return _instance
