# cooling.py - rizeni pumpy a ventilatoru Krakenu
#
# Rezim "kapalina": krivky se nahraji do Krakenu, ten je ridi sam (i bez aplikace).
# Rezim "cpu": aplikace kazdou sekundu cte teplotu CPU z HWiNFO, vyhladi ji
#   (prumer za N sekund, aby ventilatory neskakaly) a nastavi pevny vykon.
#   Pojistky:
#     - kdyz teplota CPU chybi dele nez 5 s, nahraji se zalozni krivky podle kapaliny
#     - totez, kdyz se teplota CPU 20 s vubec nezmeni (HWiNFO zamrzlo; normalne se meni
#       skoro kazdou sekundu, nejdelsi namerena pauza 3 s)
#     - pri ukonceni aplikace (Ctrl+C, zavreni okna, odhlaseni, vypnuti PC) a pri chybe
#       komunikace se taky nahraji zalozni krivky podle kapaliny
#     - vypnute rizeni = krivky podle kapaliny (nikdy nezustane posledni pevny vykon)
#     - liquidctl pridava do kazde krivky (i "pevneho" vykonu) bod 100 % od 59 °C kapaliny

import logging
import time
from collections import deque

log = logging.getLogger("rgb_lcd")

MISSING_LIMIT_S = 5
STALE_LIMIT_S = 20     # teplota CPU beze zmeny -> HWiNFO nejspis zamrzlo
RESEND_S = 30          # i beze zmeny obcas zopakovat (napr. po probuzeni)
MIN_STEP = 2           # zmena vykonu v %, od ktere se posila


def interpolate(points, x):
    pts = sorted(points)
    if not pts:
        return None
    if x <= pts[0][0]:
        return pts[0][1]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        if x <= x2:
            return y1 + (y2 - y1) * (x - x1) / (x2 - x1) if x2 != x1 else y2
    return pts[-1][1]


class Cooling:
    def __init__(self):
        # Kraken muze byt na pevnem vykonu (napr. po padu predchozi instance), dokud
        # do nej sami nenahrajeme krivky podle kapaliny. Pri reset() se nemaze.
        self.needs_fallback = True
        self.reset()

    def reset(self):
        """Po (znovu)pripojeni nebo zmene nastaveni."""
        self.samples = deque()
        self.sent = {}           # kanal -> posledni vykon
        self.sent_at = 0.0
        self.last_seen = time.monotonic()
        self.last_value = None   # posledni teplota CPU a kdy se naposledy zmenila
        self.changed_at = time.monotonic()
        self.fallback_active = False
        self.liquid_loaded = False
        self.state = {}

    def apply_liquid(self, kraken, cool, reason):
        kraken.apply_cooling(cool)
        self.liquid_loaded = True
        self.needs_fallback = False
        self.sent = {}
        log.info("Chlazeni: krivky podle kapaliny nahrany do Krakenu (%s).", reason)

    def update(self, kraken, cool, data):
        if not cool.get("zapnuto", True) or cool.get("zdroj", "cpu") != "cpu":
            off = not cool.get("zapnuto", True)
            if not self.liquid_loaded:
                self.apply_liquid(kraken, cool, "rizeni vypnuto" if off else "rezim kapalina")
            self.state = {"rezim": "vypnuto" if off else "kapalina"}
            return

        now = time.monotonic()
        item = data.get(cool.get("senzor_cpu", ""))
        stale = False
        if item is not None:
            if item["value"] != self.last_value:
                self.last_value, self.changed_at = item["value"], now
            elif now - self.changed_at > STALE_LIMIT_S:
                stale = True                     # hodnota stoji -> brat jako chybejici
        if item is None or stale:
            if (stale or now - self.last_seen > MISSING_LIMIT_S) and not self.fallback_active:
                reason = (f"teplota CPU z HWiNFO se {STALE_LIMIT_S} s nezmenila (HWiNFO zamrzlo?) - ZALOHA"
                          if stale else "chybi teplota CPU z HWiNFO - ZALOHA")
                self.apply_liquid(kraken, cool, reason)
                self.fallback_active = True
            self.state = {"rezim": "cpu", "zaloha": self.fallback_active,
                          "duvod": "zamrzla" if stale else "chybi"}
            return

        self.last_seen = now
        if self.fallback_active:
            log.info("Chlazeni: teplota CPU je zpet, rizeni podle CPU obnoveno.")
            self.fallback_active = False
            self.sent = {}

        window = float(cool.get("vyhlazeni_s", 5))
        self.samples.append((now, item["value"]))
        while self.samples and now - self.samples[0][0] > window:
            self.samples.popleft()
        temp = sum(v for _, v in self.samples) / len(self.samples)

        curves = cool.get("cpu", {})
        targets = {"pump": interpolate(curves.get("pumpa", []), temp),
                   "fan": interpolate(curves.get("ventilatory", []), temp)}
        resend = now - self.sent_at > RESEND_S
        for ch, duty in targets.items():
            if duty is None:
                continue
            duty = int(round(duty))
            if resend or ch not in self.sent or abs(duty - self.sent[ch]) >= MIN_STEP:
                self.needs_fallback = True
                kraken.set_fixed(ch, duty)
                if abs(duty - self.sent.get(ch, -100)) >= 10:
                    log.info("Chlazeni: %s %d %% (CPU %.1f °C)", "pumpa" if ch == "pump" else "ventilatory",
                             duty, temp)
                self.sent[ch] = duty
                self.sent_at = now
        self.liquid_loaded = False
        self.state = {"rezim": "cpu", "zaloha": False, "teplota": round(temp, 1),
                      "pumpa": self.sent.get("pump"), "ventilatory": self.sent.get("fan")}

    def shutdown(self, kraken, cool, reason="aplikace konci - ZALOHA"):
        """Predat rizeni Krakenu (krivky podle kapaliny), pokud muze byt na pevnem vykonu.
        Vola se pri ukonceni aplikace i pri chybe komunikace. Vrati True, kdyz je Kraken
        bezpecne na krivkach podle kapaliny."""
        if not self.needs_fallback:
            return True
        try:
            self.apply_liquid(kraken, cool, reason)
            return True
        except Exception as e:
            log.error("Nepodarilo se nahrat zalozni krivky: %s", e)
            return False
