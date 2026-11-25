"""Period-plausible German names and appearance generation by social rank."""
import random

MALE = ["Konrad", "Heinrich", "Ulrich", "Friedrich", "Otto", "Albrecht", "Dietrich", "Gerhard", "Walther",
        "Hermann", "Berthold", "Eberhard", "Rudolf", "Hans", "Kuno", "Wolfram", "Hartmann", "Gottfried", "Burkhard",
        "Lambert", "Ludwig", "Siegfried", "Engelbert", "Arnold", "Volkmar", "Hinrich", "Jakob", "Matthias",
        "Ruprecht", "Gunther", "Egon", "Ortwin", "Bernhard", "Anselm", "Lutz", "Wenzel", "Bruno", "Thilo"]
FEMALE = ["Adelheid", "Gertrud", "Mechthild", "Hildegard", "Kunigunde", "Elisabeth", "Agnes", "Irmgard",
          "Margarete", "Jutta", "Sophia", "Richenza", "Hedwig", "Gisela", "Bertha", "Ida", "Liutgard", "Gerlinde",
          "Walburga", "Anna", "Grete", "Elsbeth", "Brigitta", "Sigrun", "Ottilie"]
JOB_SURNAMES = {"smith": "Schmied", "farmer": "Bauer", "miller": "Müller", "baker": "Becker", "fisher": "Fischer",
                "woodcutter": "Holzer", "weaver": "Weber", "innkeeper": "Wirt", "merchant": "Kaufmann",
                "guard": "Wächter", "hunter": "Jäger", "miner": "Hauer", "carter": "Fuhrmann",
                "shepherd": "Schäfer", "potter": "Töpfer"}
PLACE_PARTS = ["stein", "burg", "berg", "feld", "bach", "au", "eck", "hausen", "heim", "dorf", "wald", "tal"]
PLACE_STARTS = ["Hohen", "Rot", "Schwarz", "Wolf", "Adler", "Eichen", "Linden", "Falken", "Greif", "Löwen",
                "Rabens", "Kron", "Silber"]

SKINS = [(236, 200, 170), (224, 184, 150), (210, 168, 132), (196, 150, 112), (176, 128, 96)]
HAIRS = [(60, 40, 24), (100, 70, 40), (170, 130, 70), (210, 180, 110), (40, 34, 30), (130, 60, 30), (150, 150, 150)]
DULL = [(110, 92, 70), (96, 86, 70), (120, 104, 80), (90, 96, 80), (110, 100, 90), (128, 110, 90), (86, 76, 66)]
DYED = [(56, 80, 140), (40, 110, 70), (150, 50, 50), (140, 110, 40), (90, 60, 120), (60, 110, 120)]
RICH = [(150, 24, 36), (90, 30, 110), (30, 40, 110), (20, 90, 60)]


def person_name(rng, female=False, job=None, noble=False, place=None):
    first = rng.choice(FEMALE if female else MALE)
    if noble:
        seat = place or (rng.choice(PLACE_STARTS) + rng.choice(PLACE_PARTS))
        return f"{first} von {seat}"
    if job and job in JOB_SURNAMES and rng.random() < 0.7:
        return f"{first} {JOB_SURNAMES[job]}"
    if place and rng.random() < 0.5:
        return f"{first} aus {place}"
    return first


def make_look(rng, rank_level=0, job=None, female=False, kingdom_colors=None, clergy=False, soldier=False):
    look = {
        "skin": rng.choice(SKINS),
        "hair": rng.choice(HAIRS),
        "beard": (not female) and rng.random() < 0.45,
        "boots": (60, 44, 32),
        "female": female,
    }
    if clergy:
        look["tunic"] = (40, 34, 30) if job != "bishop" else (236, 232, 222)
        look["hose"] = look["tunic"]
        look["robe"] = True
        look["hat"] = "tonsure" if job != "bishop" else "mitre"
        if job == "bishop":
            look["trim"] = (214, 178, 74)
        return look
    if rank_level <= 1:
        look["tunic"] = rng.choice(DULL)
        look["hose"] = rng.choice(DULL)
        r = rng.random()
        look["hat"] = "gugel" if r < 0.45 else "straw" if r < 0.6 and job == "farmer" else None
        look["hat_color"] = rng.choice(DULL)
    elif rank_level == 2:
        look["tunic"] = rng.choice(DYED)
        look["hose"] = rng.choice(DULL + DYED)
        look["hat"] = rng.choice(["cap", "gugel", None])
        look["hat_color"] = rng.choice(DYED)
        look["belt"] = (40, 30, 20)
    else:
        look["tunic"] = rng.choice(RICH)
        look["hose"] = rng.choice(RICH + [(30, 30, 30)])
        look["trim"] = (214, 178, 74)
        look["hat"] = "coronet" if rank_level >= 5 else None
        if rank_level >= 8:
            look["hat"] = "crown"
    if female:
        look["robe"] = True
        look["hat"] = "veil" if rank_level < 5 else look["hat"]
        look["hat_color"] = rng.choice([(236, 232, 222), (220, 210, 190)] + ([] if rank_level < 3 else RICH))
        look["beard"] = False
    if kingdom_colors and (soldier or rank_level >= 3):
        look["tabard"] = kingdom_colors
    return look
