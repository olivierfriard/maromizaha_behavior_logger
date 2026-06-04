import json

SCAN_INTERVAL_SECONDS = 5 * 60

DEFAULT_UTM_ZONE = "39K"

HOUR_VALUES = [f"{hour:02d}" for hour in range(24)]
MINUTE_VALUES = [f"{minute:02d}" for minute in range(0, 60, 5)]
NUMERIC_1_TO_20_VALUES = [str(value) for value in range(1, 21)] + ["20+"]


SCAN_FIELDS = [
    "date",
    "time",
    "group",
    "CA",
    "presence",
    "climate",
    "GPS point name",
    "h_CA",
    "h_arbre",
    "arbre",
    "dist_CA",
    "dist_CACB",
    "pos_CACB",
]

CLIMATE = [
    "Brouillard : 0",
    "Soleil : 1",
    "Légèrement nuageux : 2",
    "Ciel couvert : 3",
    "Pluie fiable : 4",
    "Pluie forte : 5",
]

LIST_FIELDS = {
    "climate": ["-"] + CLIMATE[:],
}


NUMERIC_1_TO_20_FIELDS = [
    "h_CA",
    "h_arbre",
    "dist_CA",
]

GPS_FIELDS = [
    "GPS",
    "UTM S",
    "UTM E",
    "Altitude",
    "Z ZD",
    ">10 <10 P",
    "SPV",
]

ALIMENTATION_FIELDS = [
    "time start",
    "time end",
    "arbre",
    "GPS",
    "h_CA",
    "h_arbre",
    "arbre",
    "DBH",
    "feuille",
    "consumed_part",
    "dist_CACB",
    "pos_CACB",
    "notes",
]

BEHAVIOR_FIELDS = [
    "D_AO",
    "R",
    "W",
    "SG",
    "Y",
    "SC",
    "LS",
    "PC",
    "MP",
    "MC",
    "MG",
    "MCO",
    "A",
    "T",
    "VR",
    "DPL",
    "RE",
    "G",
    "Subject_G",
    "J",
    "Subject_J",
    "C",
    "V",
    "ICN",
    "ICPL",
    "ICPA",
    "Subject_ICs",
]

with open("config.json", "r") as f_in:
    info = json.load(f_in)

LIST_FIELDS["group"] = ["-"] + info["GROUPS_LIST"]
LIST_FIELDS["arbre"] = ["-"] + info["TREE_SPECIES"]

GROUPS_COMPOSITION = info["GROUPS_COMPOSITION"]
