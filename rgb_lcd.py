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
from led import LedWorker
import mono
import screens
import systemdata
from kraken import Kraken
import ukonceni
from ukonceni import STOP, pause

BASE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(BASE, "stav.json")      # aktualni data pro okno nastaveni
STATE_EVERY_S = 1.0                          # okno nastaveni cte stav.json 1x za sekundu

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
    keep = screens.history_spans(cfg["obrazovky"])        # grafy na Krakenu
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


def write_state(data, cooling_state, hist, alpha_state, led_state, code, problems):
    try:
        tmp = STATE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"cas": time.time(), "kod": code, "data": data, "chlazeni": cooling_state,
                       "historie": hist, "alphacool": alpha_state, "led": led_state,
                       "obrazovky_chyby": problems}, f, ensure_ascii=False)
        os.replace(tmp, STATE)
    except OSError:
        pass


def render_screen(cfg, data, hist, seen_max, rot, bad):
    """Vykreslit aktualni obrazovku rotace. Chybna obrazovka (napr. typ, ktery tahle verze
    neumi) se preskoci a zapise do logu jen jednou - chyba vykresleni nesmi sahat na chlazeni
    ani spojeni s Krakenem. Vrati obrazek, nebo None (nejde vykreslit nic)."""
    try:
        lst = screens.build_list(cfg, data, seen_max)
    except Exception as e:
        if "seznam" not in bad:
            bad["seznam"] = f"seznam obrazovek: {e}"
            log.error("Seznam obrazovek nejde sestavit (%s).", e)
        lst = [{"typ": "hodiny"}]
    now = time.monotonic()
    if now >= rot["next"]:
        rot["idx"] = (rot["idx"] + 1) % len(lst) if rot["started"] else 0
        rot["next"] = now + float(cfg["rotace_s"])
        rot["started"] = True
    for _ in range(len(lst)):
        rot["idx"] %= len(lst)
        scr = lst[rot["idx"]]
        key = json.dumps(scr, sort_keys=True, ensure_ascii=False)
        try:
            return screens.render(scr, data, cfg["velikost_obsahu"], cfg["gama_grafiky"],
                                  cfg.get("velikost_textu", 1.0), hist)
        except Exception as e:
            if scr.get("typ") not in screens.DRAW:
                e = "tahle verze aplikace typ nezná - restartuj aplikaci"
            if key not in bad:
                bad[key] = f"{screens.TYPES.get(scr.get('typ'), scr.get('typ'))}: {e}"
                log.error("Obrazovku %s nejde vykreslit (%s) - preskakuji ji.", scr.get("typ"), e)
            rot["idx"] += 1                      # zkusit dalsi obrazovku v rotaci
    try:                                         # nejde vykreslit nic: aspon hodiny
        return screens.render({"typ": "hodiny"}, data, 0.92, cfg.get("gama_grafiky", 0.65))
    except Exception:
        return None


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
    rot = {"idx": 0, "next": 0.0, "started": False}     # rotace obrazovek
    bad_screens = {}                                   # obrazovky, ktere nejde vykreslit (klic -> chyba)
    last_bytes = None
    last_state = 0.0
    code = config.code_stamp()                         # verze kodu - okno nastaveni pozna starou verzi
    warned_hwinfo = False
    alpha = AlphacoolWorker()            # vlastni vlakno - chlazeni nezdrzuje
    alpha.start()
    leds = LedWorker()                   # LED ventilatoru a desky, taky vlastni vlakno
    leds.start()
    leds.update(cfg["led"])
    ukonceni.on_power(suspend=leds.blackout, resume=leds.resume)   # spanek: LED zhasnout

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
                    bad_screens.clear()
                    last_bytes = None
                    if cfg["jas"] != old_jas:
                        kraken.set_brightness(cfg["jas"])
                    log.info("Nastaveni nacteno znovu.")

                data = collect(kraken)
                cooling.update(kraken, cfg["chlazeni"], data)
                hist = update_history(history, cfg, data)
                alpha.update(cfg["alphacool"], data, hist, cfg["obnova_s"])
                leds.update(cfg["led"], data)
                if time.monotonic() - last_state >= STATE_EVERY_S:
                    write_state(data, cooling.state, hist, alpha.state, leds.state, code,
                                sorted(bad_screens.values()))
                    last_state = time.monotonic()
                if not any(not k.startswith("@") for k in data) and not warned_hwinfo:
                    log.warning("Z HWiNFO nejsou data - bezi HWiNFO se zapnutym Gadget reportingem?")
                    warned_hwinfo = True
                for name, item in data.items():
                    seen_max[name] = max(seen_max.get(name, item["value"]), item["value"])

                img = render_screen(cfg, data, hist, seen_max, rot, bad_screens)
                if img is not None:
                    b = img.tobytes()
                    if b != last_bytes:          # posilame jen zmeny
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
            # az po predani chlazeni - to ma prednost; pri vypnuti PC LED zhasnout
            leds.stop(0.5, off=ukonceni.SHUTDOWN.is_set())
            alpha.stop(1.5)
        finally:
            ukonceni.DONE.set()


if __name__ == "__main__":
    main()
