"""Bilingual NPC speech. Markup: [Deutsch|english] marks a German word with its gloss.

Lines mix English and German so you can understand everything from context while the German
words stick. Every word you hear is recorded in your Wörterbuch (dictionary) with a count.
Tokens: {addr} = how they address you by rank, {you} = du/Ihr (informal/formal), {name}, {place},
{lord}, {realm}, {enemy}, {price}.
"""
import random
import re

TOKEN = re.compile(r"\[([^\]|]+)\|([^\]]*)\]")

LINES = {
    "greet_morning": [
        "[Guten Morgen|good morning], {addr}!",
        "[Morgen|morning]! The [Hahn|rooster] woke me before the [Sonne|sun].",
        "[Guten Morgen|good morning]. Did {you} sleep well? [Gut geschlafen|slept well]?",
    ],
    "greet_day": [
        "[Guten Tag|good day], {addr}.",
        "[Grüß Gott|God greet you], {addr}!",
        "[Hallo|hello]! A fine [Tag|day] in {place}.",
        "[Gott zum Gruße|God's greeting to you], {addr}.",
    ],
    "greet_evening": [
        "[Guten Abend|good evening], {addr}.",
        "The [Abend|evening] comes. Soon the [Glocke|bell] rings for [Vesper|vespers].",
    ],
    "greet_night": [
        "[Gute Nacht|good night]… why are {you} out in the [Dunkelheit|darkness]?",
        "Pssst! It's [Nacht|night]. The [Wölfe|wolves] are hungry.",
    ],
    "farewell": [
        "[Auf Wiedersehen|goodbye]!", "[Behüt dich Gott|God protect you]!", "[Bis bald|see you soon], {addr}.",
        "[Gehab dich wohl|fare thee well].",
    ],
    "farmer": [
        "The [Weizen|wheat] grows tall this [Sommer|summer].",
        "[Regen|rain] is good for the [Acker|field], bad for my [Rücken|back].",
        "Half my [Ernte|harvest] goes to the [Herr|lord], a tenth to the [Kirche|church]. The [Zehnt|tithe]!",
        "My [Kuh|cow] gives good [Milch|milk]. [Gott sei Dank|thank God].",
        "[Säen|to sow] in [Frühling|spring], [ernten|to harvest] in [Herbst|autumn]. That is life.",
    ],
    "smith": [
        "The [Eisen|iron] must be [heiß|hot] before I strike it.",
        "A good [Schwert|sword] costs three [Barren|bars] of [Eisen|iron].",
        "[Hammer|hammer] and [Amboss|anvil], all day long. Klang! Klang!",
        "Bring me [Erz|ore] and [Kohle|coal] and I will make {you} anything.",
    ],
    "miller": ["The [Wind|wind] turns my [Mühle|mill]. No wind, no [Mehl|flour].",
               "[Mehl|flour] for [Brot|bread]. Everyone needs [Brot|bread]."],
    "baker": ["Fresh [Brot|bread]! Still [warm|warm] from the [Ofen|oven]!", "One [Laib|loaf] for two [Pfennig|pennies]."],
    "fisher": [
        "The [Meer|sea] gives [Fisch|fish] — and takes [Männer|men].",
        "My [Boot|boat] is old, but the [Netz|net] is new.",
        "When the [Möwen|gulls] fly inland, a [Sturm|storm] is coming.",
    ],
    "woodcutter": ["[Holz|wood] for the [Winter|winter]. Chop, chop.", "The [Wald|forest] belongs to the [Herzog|duke]. I only cut what he allows."],
    "miner": ["Deep in the [Berg|mountain] there is [Silber|silver].", "No [Licht|light] down there but my [Fackel|torch].",
              "[Glück auf|good luck — miner's greeting]!"],
    "shepherd": ["My [Schafe|sheep] give [Wolle|wool]. [Wolle|wool] becomes [Tuch|cloth]."],
    "weaver": ["[Tuch|cloth] from [Wolle|wool], thread by thread."],
    "innkeeper": [
        "[Bier|beer] or [Wein|wine], {addr}? [Prost|cheers]!",
        "Sit, sit! The [Suppe|soup] is hot.",
        "[Willkommen|welcome] to my [Wirtshaus|inn]!",
    ],
    "merchant": [
        "[Kaufen|buy] or [verkaufen|sell]? I do both!",
        "[Salz|salt] from the [Küste|coast], [Silber|silver] from the [Berge|mountains]. All good [Ware|wares]!",
        "That costs {price} [Pfennig|pennies]. A fair [Preis|price]!",
        "[Zu teuer|too expensive]? Bah! Go to {place} and see their prices.",
    ],
    "guard": [
        "[Halt|stop]! Who goes there? … Ah, {addr}. Pass.",
        "Keep the [Frieden|peace] in the [Stadt|town].",
        "The [Tor|gate] closes at [Sonnenuntergang|sunset].",
        "No [Waffen|weapons] drawn inside the [Mauern|walls]!",
    ],
    "soldier": [
        "For {lord} and {realm}!",
        "Our [Feinde|enemies] in {enemy} sharpen their [Speere|spears].",
        "In the [Schildwall|shield wall], your [Schild|shield] guards your [Nachbar|neighbour].",
        "[Achtung|attention]! Eyes open.",
    ],
    "knight": [
        "A [Ritter|knight] serves his [Herr|lord] and protects the [Schwachen|weak].",
        "My [Pferd|horse] is worth more than my [Burg|castle].",
        "[Ehre|honour] is the only [Reichtum|wealth] that cannot be stolen.",
    ],
    "noble": [
        "I hold this [Lehen|fief] from {lord}. The [Bauern|peasants] feed my [Ritter|knights].",
        "[Steuern|taxes] are late again. The [Ernte|harvest] was poor.",
        "Kneel, {addr}… or don't. These are new times.",
    ],
    "ruler": [
        "I am one of the seven [Kurfürsten|prince-electors]. My [Stimme|vote] makes the [Kaiser|emperor].",
        "{enemy} wants my [Krone|crown]. They shall have my [Schwert|sword] instead.",
        "Serve me well, and I will grant {you} [Land|land].",
    ],
    "priest": [
        "[Gott|God] sees all, {addr}.",
        "[Bete|pray] and [arbeite|work] — ora et labora.",
        "The [Glocke|bell] calls to [Messe|mass].",
        "The [Abgrund|abyss] is a [Prüfung|test] from [Gott|God].",
    ],
    "monk": ["[Friede sei mit dir|peace be with you], my [Bruder|brother].", "We copy [Bücher|books] by [Kerzenlicht|candlelight]."],
    "beggar": ["A [Pfennig|penny] for a poor [Mann|man]? [Bitte|please]…", "[Hunger|hunger]… so much [Hunger|hunger]."],
    "child": ["[Spielen|play] with me!", "My [Mutter|mother] says the [Abgrund|abyss] eats bad [Kinder|children]!",
              "Is that a real [Schwert|sword]?"],
    "carter": ["My [Wagen|cart] goes to {place}. [Einsteigen|get in] — for a fee."],
    "huntsman": ["[Wild|game] in the [Wald|forest] belongs to the [Herr|lord]. Poaching is [verboten|forbidden]."],
    # weather & world
    "rain": ["[Es regnet|it's raining]! My [Schuhe|shoes] are [nass|wet].", "[Regen|rain], [Regen|rain], always [Regen|rain]."],
    "storm": ["[Sturm|storm]! Get inside!", "[Blitz|lightning] and [Donner|thunder]! [Gott|God] is angry."],
    "snow": ["[Schnee|snow]! It's [kalt|cold]. [Brrr|brrr]."],
    "fog": ["[Nebel|fog]… I can't see my own [Hand|hand]."],
    "sunny": ["What a [schöner Tag|beautiful day]!", "The [Sonne|sun] is [warm|warm] today."],
    "windy": ["The [Wind|wind] is strong. Good for [Segel|sails] and [Mühlen|mills]."],
    "abyss": ["Don't go near the [Rand|edge]! The [Abgrund|abyss] takes everything.",
              "Last [Winter|winter] the [Abgrund|abyss] ate the [Hof|farm] of old Lambert.",
              "They say who falls into the [Abgrund|abyss] falls out of the [Himmel|sky] somewhere else…"],
    "lava": ["[Feuer|fire] from the earth. The [Glutmeer|fire sea] burns forever.",
             "[Heiß|hot]! Too [heiß|hot] here."],
    "war": ["[Krieg|war] with {enemy}. They burned three [Dörfer|villages].",
            "The [Heer|army] marches. Pray for our [Söhne|sons]."],
    "rumor": ["[Hast du gehört|have you heard]? The [Abgrund|abyss] grows every [Jahr|year].",
              "The [Kaiser|emperor] is dead and the seven [Kurfürsten|electors] cannot agree.",
              "[Markgraf|margrave] Otto der Rote wants to be [Kaiser|emperor]. [Gott|God] help us.",
              "In Frostholm they keep a [Chronik|chronicle] older than the [Welt|world] itself."],
    # reactions
    "afraid": ["[Hilfe|help]!", "[Lauft|run]!", "[Gnade|mercy]!", "Don't hurt me, [bitte|please]!"],
    "fire": ["[Feuer|fire]! [Feuer|fire]! Bring [Wasser|water]!", "It [brennt|is burning]!"],
    "thief": ["[Dieb|thief]! [Haltet den Dieb|stop the thief]!"],
    "crime": ["[Halt|stop]! [Im Namen des Gesetzes|in the name of the law]!", "[Verbrecher|criminal]! Seize him!"],
    "bow": ["[Euer Gnaden|your grace]…", "[Zu Diensten|at your service], {addr}.", "[Verzeihung|forgive me], {addr}!"],
    "battle": ["[Angriff|attack]!", "[Für|for] {realm}!", "[Haltet die Linie|hold the line]!", "[Tod|death] to {enemy}!",
               "[Zu mir|to me]!", "[Vorwärts|forward]!"],
    "hurt": ["[Au|ow]!", "[Verflucht|cursed]!", "Argh!"],
    "victory": ["[Sieg|victory]!", "[Gott mit uns|God with us]!"],
    "trade_ok": ["[Danke|thank you]! [Gutes Geschäft|good deal]."],
    "trade_poor": ["{you} have no [Geld|money]! [Kein Geld|no money], [keine Ware|no goods]."],
}

# commands shouted by commanders — learn these and you can lead an army in German
ORDERS = {
    "vorwaerts": ("[Vorwärts|forward]!", "Advance"),
    "halt": ("[Halt|halt]!", "Hold position"),
    "angriff": ("[Angriff|attack]!", "Charge"),
    "zurueck": ("[Zurück|back]!", "Fall back"),
    "schildwall": ("[Schildwall|shield wall]!", "Shield wall: blocks arrows, slow"),
    "igel": ("[Igel|hedgehog]!", "Pike hedge: stops cavalry dead"),
    "keil": ("[Keil|wedge]!", "Wedge: breaks lines, weak flanks"),
    "locker": ("[Locker|loose]!", "Loose order: arrows miss, weak in melee"),
    "salve": ("[Schießt|shoot]! [Salve|volley]!", "Archers fire volleys"),
    "wechsel": ("[Wechsel|switch]!", "Rotate the front rank"),
    "folgt": ("[Mir nach|follow me]!", "Follow your commander"),
    "formiert": ("[Formiert euch|form up]!", "Gather followers into a block"),
    "aufloesen": ("[Auflösen|disperse]!", "Break formation"),
}


def parse(text):
    """-> (segments, glosses). segments: list of (str, german:bool)."""
    segs = []
    gl = []
    pos = 0
    for m in TOKEN.finditer(text):
        if m.start() > pos:
            segs.append((text[pos:m.start()], False))
        segs.append((m.group(1), True))
        gl.append((m.group(1), m.group(2)))
        pos = m.end()
    if pos < len(text):
        segs.append((text[pos:], False))
    return segs, gl


def plain(text):
    return TOKEN.sub(lambda m: m.group(1), text)


def fill(line, ctx):
    from .ranks import address
    lvl = ctx.get("player_rank", 0)
    a_de, a_en, du = address(lvl)
    rep = {
        "{addr}": f"[{a_de}|{a_en}]",
        "{you}": "[du|you]" if du else "[Ihr|you (polite)]",
        "{name}": ctx.get("name", "Fremder"),
        "{place}": ctx.get("place", "hier"),
        "{lord}": ctx.get("lord", "unser Herr"),
        "{realm}": ctx.get("realm", "das Reich"),
        "{enemy}": ctx.get("enemy", "Glutmark"),
        "{price}": str(ctx.get("price", 3)),
    }
    for k, v in rep.items():
        line = line.replace(k, v)
    return line


def pick(cat, ctx, rng=random):
    opts = LINES.get(cat)
    if not opts:
        return None
    return fill(rng.choice(opts), ctx)


class Woerterbuch:
    """Your personal German dictionary: every word you've heard, and how often."""

    def __init__(self):
        self.words = {}   # de -> [en, count, first_heard_context]

    def learn(self, text, context=""):
        _, gl = parse(text)
        new = []
        for de, en in gl:
            e = self.words.get(de)
            if not en:
                en = e[0] if e else ""
            if e is None:
                self.words[de] = [en, 1, context]
                new.append((de, en))
            else:
                e[1] += 1
        return new

    def sorted(self):
        return sorted(self.words.items(), key=lambda kv: kv[0].lower())
