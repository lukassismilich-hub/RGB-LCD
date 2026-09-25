# rgb_lcd.py - dashboard na displej NZXT Kraken 2023
# Spusteni: py rgb_lcd.py   (ukonceni Ctrl+C nebo zavrenim okna - chlazeni prevezme
#           Kraken podle krivek kapaliny, displej se vrati na teplotu kapaliny)
#           Bez konzole: pythonw rgb_lcd.py (tak ji spousti autostart), ukonceni ukoncit.bat.
# Nastaveni: nastaveni.bat - zmeny se projevi za behu, bez restartu.

import json
import logging
import logging.handlers
import os
import sys
import time
from collections import deque

from alphacool import AlphacoolWorker
import camservice
import config
from cooling import Cooling
import hwinfo
import mono
import screens
import systemdata
from kraken import Kraken
import ukonceni
from ukonceni import STOP, pause

BASE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(BASE, "stav.json")      # aktualni data pro okno nastaveni

log = logging.getLogger("rgb_lcd")


def setup_logging():
    handlers = [logging.handlers.RotatingFileHandler(
        os.path.join(BASE, "rgb_lcd.log"), maxBytes=1_000_000, backupCount=3, encoding="utf-8")]
    if sys.stdout is not None:                   # pythonw (autostart) nema konzoli
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=handlers)
    # liquidctl pise pri kazdem nastaveni vykonu 40 radku krivky - staci varovani a chyby
    logging.getLogger("liquidctl").setLevel(logging.WARNING)

    def excepthook(exc_type, exc, tb):           # bez konzole by chyba zmizela
        log.critical("Neosetrena chyba:", exc_info=(exc_type, exc, tb))
    sys.excepthook = excepthook


def hand_over(kraken, cooling, cool, reason):
    """Predat chlazeni Krakenu (krivky podle kapaliny). Kdyz neni pripojeny, zkusi se
    pripojit - jinak by mohl zustat na poslednim pevnem vykonu."""
    if not cooling.needs_fallback:
        return
    if kraken.dev is None:
        try:
            kraken.open()
        except Exception as e:
            log.error("Zalozni krivky nejde nahrat, Kraken neni pripojeny: %s", e)
            return
    cooling.shutdown(kraken, cool, reason)


def collect(kraken):
    data = hwinfo.read_full()
    data.update(systemdata.read())          # disky, sit, Wi-Fi (HWiNFO je neposila)
    data.update(kraken.status())
    return data



def update_history(history, cfg, data):
    """Historie hodnot pro obrazovky typu graf: {senzor: deque[(cas, hodnota)]}"""
    now = time.monotonic()
    keep = {}
    for s in cfg["obrazovky"]:
        if s.get("typ") == "graf" and s.get("senzor"):
            keep[s["senzor"]] = max(keep.get(s["senzor"], 0), float(s.get("delka_s", 120)))
    for name, span in mono.graph_sensors(cfg.get("alphacool", {})).items():   # grafy na Alphacoolu
        keep[name] = max(keep.get(name, 0), span)
    for name in list(history):
        if name not in keep:
            del history[name]
    for name, span in keep.items():
        dq = history.setdefault(name, deque())
        item = data.get(name)
        if item is not None:
            dq.append((now, item["value"]))
        while dq and now - dq[0][0] > span:
            dq.popleft()
    return {k: [v for _, v in dq] for k, dq in history.items()}


def write_state(data, cooling_state, hist, alpha_state):
    try:
        tmp = STATE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"cas": time.time(), "data": data, "chlazeni": cooling_state,
                       "historie": hist, "alphacool": alpha_state}, f, ensure_ascii=False)
        os.replace(tmp, STATE)
    except OSError:
        pass


def main():
    setup_logging()
    if not ukonceni.single_instance():
        log.warning("Aplikace uz bezi (nejspis z automatickeho spusteni) - druha instance konci. "
                    "Ukoncit ji jde pres ukoncit.bat.")
        return
    ukonceni.install()
    log.info("Start aplikace.")
    camservice.stop()
    cfg = config.load()
    cfg_time = config.mtime()
    kraken = Kraken(cfg["jas"], cfg.get("dvojite_odesilani", False))
    cooling = Cooling()
    history = {}
    seen_max = {}
    idx = 0
    next_switch = 0.0
    last_bytes = None
    current_key = None
    warned_hwinfo = False
    alpha = AlphacoolWorker()            # vlastni vlakno - chlazeni nezdrzuje
    alpha.start()

    try:
        while not STOP.is_set():
            loop_start = time.monotonic()
            try:
                if kraken.dev is None:
                    kraken.open()
                    last_bytes = None
                    log.info("Kraken pripojen.")
                    cooling.reset()

                # zmena nastaveni za behu
                if config.mtime() != cfg_time:
                    cfg_time = config.mtime()
                    old_jas = cfg["jas"]
                    old_cool = cfg.get("chlazeni")
                    cfg = config.load()
                    if cfg.get("chlazeni") != old_cool:
                        cooling.reset()
                    screens.clear_cache()
                    last_bytes = None
                    if cfg["jas"] != old_jas:
                        kraken.set_brightness(cfg["jas"])
                    log.info("Nastaveni nacteno znovu.")

                data = collect(kraken)
                cooling.update(kraken, cfg["chlazeni"], data)
                hist = update_history(history, cfg, data)
                alpha.update(cfg["alphacool"], data, hist, cfg["obnova_s"])
                write_state(data, cooling.state, hist, alpha.state)
                if not any(not k.startswith("@") for k in data) and not warned_hwinfo:
                    log.warning("Z HWiNFO nejsou data - bezi HWiNFO se zapnutym Gadget reportingem?")
                    warned_hwinfo = True
                for name, item in data.items():
                    seen_max[name] = max(seen_max.get(name, item["value"]), item["value"])

                lst = screens.build_list(cfg, data, seen_max)
                now = time.monotonic()
                if now >= next_switch:
                    idx = (idx + 1) % len(lst) if current_key is not None else 0
                    next_switch = now + float(cfg["rotace_s"])
                idx %= len(lst)
                scr = lst[idx]
                current_key = json.dumps(scr, sort_keys=True)

                img = screens.render(scr, data, cfg["velikost_obsahu"], cfg["gama_grafiky"],
                                     cfg.get("velikost_textu", 1.0), hist)
                b = img.tobytes()
                if b != last_bytes:              # posilame jen zmeny
                    kraken.show(img)
                    last_bytes = b

            except KeyboardInterrupt:
                raise
            except Exception as e:
                log.error("Chyba: %s - zkusim znovu za 5 s", e)
                if "CAMService" in str(e):       # sluzbu mohl znovu spustit NZXT CAM
                    camservice.stop()
                if kraken.dev is not None:       # nenechat Kraken na pevnem vykonu
                    cooling.shutdown(kraken, cfg["chlazeni"], "chyba komunikace - ZALOHA")
                kraken.close(back_to_liquid=False)
                pause(5)
                continue

            elapsed = time.monotonic() - loop_start
            period = max(config.MIN_REFRESH_S, float(cfg["obnova_s"]))
            pause(max(0.05, period - elapsed))
    except KeyboardInterrupt:
        log.info("Ukoncuji (Ctrl+C).")
    finally:
        try:
            hand_over(kraken, cooling, cfg["chlazeni"], "aplikace konci - ZALOHA")
            kraken.close()
            alpha.stop(1.5)                  # az po predani chlazeni - to ma prednost
        finally:
            ukonceni.DONE.set()


if __name__ == "__main__":
    main()
