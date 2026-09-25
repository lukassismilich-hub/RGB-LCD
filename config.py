# config.py - nacteni, prevod ze stare verze a ulozeni nastaveni (config.json)

import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(BASE, "config.json")

LIQUID = "@kapalina"       # teplota kapaliny primo z Krakenu

DEFAULT_SCREENS = [
    {"typ": "dva_bary", "zapnuto": True,
     "nadpis1": "CPU", "senzor1": "CPU (Tctl/Tdie)", "bar1_od": "#3cff3c", "bar1_do": "#3cff3c",
     "min1": 0, "max1": 100,
     "nadpis2": "GPU", "senzor2": "Teplota GPU", "bar2_od": "#3264ff", "bar2_do": "#3264ff",
     "min2": 0, "max2": 100,
     "jednotka": "°", "delitel": 1, "desetinna_mista": 0},
    {"typ": "oblouk", "zapnuto": True, "nadpis": "Liquid", "senzor": LIQUID,
     "min": 25, "max": 50, "jednotka": "°", "delitel": 1, "desetinna_mista": 0},
    {"typ": "dva_bary", "zapnuto": True,
     "nadpis1": "CPU", "senzor1": "Takt jader", "bar1_od": "#b4f014", "bar1_do": "#b4f014",
     "min1": 0, "max1": 5.5,
     "nadpis2": "GPU", "senzor2": "Takt GPU", "bar2_od": "#ff9614", "bar2_do": "#ff9614",
     "min2": 0, "max2": 3.2,
     "jednotka": "GHz", "delitel": 1000, "desetinna_mista": 1},
    {"typ": "hodiny", "zapnuto": True},
]

DEFAULTS = {
    "jas": 100,
    "velikost_obsahu": 0.92,
    "velikost_textu": 1.0,
    "gama_grafiky": 0.65,
    "rotace_s": 5,
    "obnova_s": 1,
    "auto_obrazovky": True,
    "skryte_senzory": [],
    "obrazovky": DEFAULT_SCREENS,
    "dvojite_odesilani": False,
    # krivky: [teplota kapaliny °C, vykon %]; pumpa min. 20 %, nad 59 °C vzdy 100 %
    "chlazeni": {
        "zapnuto": True,
        # "cpu" = aplikace ridi podle teploty CPU z HWiNFO (jako CAM)
        # "kapalina" = krivky se nahraji do Krakenu a ten ridi sam
        "zdroj": "cpu",
        "senzor_cpu": "CPU (Tctl/Tdie)",
        "vyhlazeni_s": 5,
        "cpu": {
            "pumpa": [[20, 20], [75, 20], [80, 45], [85, 75], [90, 100]],
            "ventilatory": [[20, 10], [75, 10], [80, 30], [85, 30], [90, 65], [95, 100]],
        },
        # krivky podle kapaliny - pouziji se v rezimu "kapalina" a jako ZALOHA,
        # kdyz aplikace skonci nebo HWiNFO prestane posilat teplotu CPU
        "pumpa": [[20, 60], [30, 70], [35, 80], [40, 90], [45, 100]],
        "ventilatory": [[25, 25], [30, 35], [35, 50], [40, 70], [45, 90], [50, 100]],
    },
}


def _migrate(old):
    """Prevod configu z prvni verze (klice hwinfo / rozsahy / poradi)."""
    cfg = json.loads(json.dumps(DEFAULTS))
    for k in ("jas", "velikost_obsahu", "gama_grafiky", "rotace_s", "dvojite_odesilani"):
        if k in old:
            cfg[k] = old[k]
    hw = old.get("hwinfo", {})
    r = old.get("rozsahy", {})
    s = cfg["obrazovky"]
    s[0]["senzor1"] = hw.get("cpu_temp", s[0]["senzor1"])
    s[0]["senzor2"] = hw.get("gpu_temp", s[0]["senzor2"])
    s[1]["min"], s[1]["max"] = r.get("kapalina_c", [25, 50])
    s[2]["senzor1"] = hw.get("cpu_clock_mhz", s[2]["senzor1"])
    s[2]["senzor2"] = hw.get("gpu_clock_mhz", s[2]["senzor2"])
    s[2]["max1"] = r.get("cpu_ghz_max", 5.5)
    s[2]["max2"] = r.get("gpu_ghz_max", 3.2)
    return cfg


def load():
    try:
        with open(PATH, encoding="utf-8") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        cfg = {}
    if "obrazovky" not in cfg:
        cfg = _migrate(cfg)
        save(cfg)
    for k, v in DEFAULTS.items():
        cfg.setdefault(k, json.loads(json.dumps(v)))
    for k, v in DEFAULTS["chlazeni"].items():          # doplneni novych klicu chlazeni
        cfg["chlazeni"].setdefault(k, json.loads(json.dumps(v)))
    for scr in cfg["obrazovky"]:                        # stare jednobarevne bary -> prechod od/do
        for n in ("1", "2"):
            if "barva" + n in scr:
                col = scr.pop("barva" + n)
                scr.setdefault(f"bar{n}_od", col)
                scr.setdefault(f"bar{n}_do", col)
    for scr in cfg["obrazovky"]:                        # kazda obrazovka ma vlastni velikosti
        scr.setdefault("velikost_obsahu", cfg["velikost_obsahu"])
        if scr.get("typ") != "hodiny":
            scr.setdefault("velikost_textu", cfg["velikost_textu"])
    return cfg


def save(cfg):
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PATH)


def mtime():
    try:
        return os.path.getmtime(PATH)
    except OSError:
        return 0
