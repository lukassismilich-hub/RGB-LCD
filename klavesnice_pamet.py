# klavesnice_pamet.py - podsviceni v integrovane pameti G815 (onboard profily 1-3 = M1-M3)
#
# Profil (sektor 1-3, 256 B, format 4): od bajtu 208 ctyri zaznamy podsviceni po 11 B - klavesy, logo,
# klavesy v usporem rezimu, logo v usporem rezimu (G HUB tam dava stejny efekt s jasem 50 %).
# Na konci sektoru CRC-16/CCITT (init 0xFFFF) pres bajty 0-253, big endian. Zaznamy (overeno na
# obsahu pameti 9. 11. 2026, formaty podle libratbag hidpp20):
#   00 ...                                    vypnuto
#   01 R G B 00 ...                           jedna barva (bez jasu - jas = ztlumena barva)
#   03 00 00 00 00 00 periodaH periodaL jas   cyklus barev (perioda ms, jas 1-100)
#   0A R G B periodaH periodaL 01 jas         dychani (perioda ms, prubeh 1, jas 1-100)
#   04 / 0C ...                               vlna / jiny efekt z G HUB - neznamy format, jen se ukaze
# Zapis (HID++ 0x8100): funkce 6 memoryAddrWrite [sektor, offset 0, delka], 7 memoryWrite po 16 B,
# 8 memoryWriteEnd - jako G HUB / libratbag. Pred zapisem zaloha, po zapisu cteni a porovnani.
# Pamet ma jen vestavene efekty: barvy jednotlivych klaves, casti a efekty aplikace se ulozit nedaji.

import logging

import klavesnice as K

log = logging.getLogger("rgb_lcd")

LIGHT_OFF = 208                                   # zacatek zaznamu podsviceni v profilu
LIGHT_LEN = 11
SECTOR = 256
TYPES = [("vypnuto", "vypnuto"), ("barva", "jedna barva"), ("dychani", "dýchání"), ("cyklus", "cyklus barev")]
SAVE_JAS = 50                                     # usporny rezim: stejny efekt s timto jasem (jako G HUB)


def crc16(data):
    c = 0xFFFF
    for b in data:
        c ^= b << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
    return c


def _rgb(h):
    h = str(h or "#ffffff").lstrip("#")
    try:
        return [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    except ValueError:
        return [255, 255, 255]


def encode(e):
    """Efekt {"typ", "barva", "perioda_s", "jas"} -> 11 B zaznamu."""
    typ = e.get("typ", "cyklus")
    jas = max(1, min(100, int(e.get("jas", 100))))
    per = max(500, min(20000, int(round(float(e.get("perioda_s", 3.0)) * 1000))))
    out = [0] * LIGHT_LEN
    if typ == "barva":
        out[0] = 0x01
        out[1:4] = [round(v * jas / 100) for v in _rgb(e.get("barva"))]
    elif typ == "dychani":
        out[0] = 0x0A
        out[1:4] = _rgb(e.get("barva"))
        out[4:8] = [per >> 8, per & 0xFF, 0x01, jas]
    elif typ == "cyklus":
        out[0] = 0x03
        out[6:9] = [per >> 8, per & 0xFF, jas]
    return bytes(out)


def decode(b):
    """11 B zaznamu -> efekt (pro okno); neznamy typ = {"typ": "jiny", "kod"}."""
    b = bytes(b)
    t = b[0]
    if t == 0x00:
        return {"typ": "vypnuto"}
    if t == 0x01:
        return {"typ": "barva", "barva": "#%02x%02x%02x" % tuple(b[1:4]), "jas": 100}
    if t == 0x03:
        return {"typ": "cyklus", "perioda_s": ((b[6] << 8) | b[7]) / 1000, "jas": b[8]}
    if t == 0x0A:
        return {"typ": "dychani", "barva": "#%02x%02x%02x" % tuple(b[1:4]),
                "perioda_s": ((b[4] << 8) | b[5]) / 1000, "jas": b[7]}
    return {"typ": "jiny", "kod": t}


def describe(e):
    t = e.get("typ")
    if t == "vypnuto":
        return "vypnuto"
    if t == "barva":
        return f"jedna barva {e.get('barva')}"
    if t == "dychani":
        return f"dýchání {e.get('barva')} {e.get('perioda_s', 0):g} s, jas {e.get('jas')} %"
    if t == "cyklus":
        return f"cyklus barev {e.get('perioda_s', 0):g} s, jas {e.get('jas')} %"
    return {0x04: "vlna (z G HUB)", 0x0C: "efekt z G HUB"}.get(e.get("kod"), f"efekt z G HUB (typ {e.get('kod')})")


def with_lights(sector, keys, logo):
    """Obsah sektoru profilu s novym podsvicenim (klavesy, logo, a totez s jasem SAVE_JAS) a CRC."""
    s = bytearray(sector)
    if len(s) != SECTOR:
        raise ValueError("sektor profilu nemá 256 B")
    recs = [keys, logo, dict(keys, jas=min(SAVE_JAS, int(keys.get("jas", 100)))),
            dict(logo, jas=min(SAVE_JAS, int(logo.get("jas", 100))))]
    for i, e in enumerate(recs):
        if e.get("typ") not in dict(TYPES):           # neznamy efekt z G HUB: zaznam nechat, jak je
            continue
        s[LIGHT_OFF + LIGHT_LEN * i:LIGHT_OFF + LIGHT_LEN * (i + 1)] = encode(e)
    c = crc16(s[:SECTOR - 2])
    s[SECTOR - 2], s[SECTOR - 1] = c >> 8, c & 0xFF
    return bytes(s)


def read_lights(k=None):
    """{1: (klavesy, logo), 2: ..., 3: ...} z pameti klavesnice (jen cteni)."""
    def go(k):
        out = {}
        for m in (1, 2, 3):
            s = bytes(k.read_sector(m, SECTOR))
            out[m] = (decode(s[LIGHT_OFF:LIGHT_OFF + LIGHT_LEN]),
                      decode(s[LIGHT_OFF + LIGHT_LEN:LIGHT_OFF + 2 * LIGHT_LEN]))
        return out
    if k is not None:
        return go(k)
    with K.G815() as k:
        return go(k)


def write_sector(k, sector, data):
    """Zapsat cely sektor (HID++ 0x8100 funkce 6 / 7 / 8) a overit ctenim."""
    idx = k.feature(K.FEATURE_ONBOARD)
    data = bytes(data)
    if len(data) != SECTOR or crc16(data[:SECTOR - 2]) != (data[-2] << 8 | data[-1]):
        raise ValueError("sektor nemá platný kontrolní součet – nezapisuji")
    k.request(idx, 6, [sector >> 8, sector & 0xFF, 0, 0, SECTOR >> 8, SECTOR & 0xFF])
    for off in range(0, SECTOR, 16):
        k.request(idx, 7, list(data[off:off + 16]))
    k.request(idx, 8)
    back = bytes(k.read_sector(sector, SECTOR))
    if back != data:
        raise K.HidppError(f"sektor {sector}: po zápisu se obsah liší (zálohu lze vrátit)")


def write_lights(lights, progress=None):
    """lights = {m: (klavesy, logo)} -> zapsat do profilu m (1-3). Nejdriv zaloha cele pameti.
    Vrati cestu k zaloze."""
    path = K.backup_memory()
    with K.G815() as k:
        desc = k.memory_description()
        if desc["format_profilu"] != 4 or desc["velikost_sektoru"] != SECTOR:
            raise K.HidppError(f"neznámý formát paměti ({desc}) – nezapisuji")
        for n, (m, (keys, logo)) in enumerate(sorted(lights.items())):
            if m not in (1, 2, 3):
                continue
            cur = bytes(k.read_sector(m, SECTOR))
            if crc16(cur[:SECTOR - 2]) != (cur[-2] << 8 | cur[-1]):
                raise K.HidppError(f"profil {m} v paměti nemá platný kontrolní součet – nezapisuji")
            new = with_lights(cur, keys, logo)
            if new != cur:
                write_sector(k, m, new)
            if progress:
                progress(n + 1, len(lights))
    log.info("%s: podsvícení profilů %s zapsáno do integrované paměti (záloha %s).", K.NAME,
             ", ".join(f"M{m}" for m in sorted(lights)), path)
    return path


def suggest(prof):
    """Navrh efektu do pameti podle nastaveni M (profil klavesy_g): (klavesy, logo)."""
    import klavesnice_efekty as kbfx
    eff = prof.get("efekt_klavesnice") or {}
    typ = eff.get("typ")
    jas = int((prof.get("klavesnice") or {}).get("jas", 100))
    pal = kbfx.palette(eff) if hasattr(kbfx, "palette") else eff.get("barvy") or ["#ffffff"]
    first = (pal or ["#ffffff"])[0]
    try:
        speed = max(1.0, min(10.0, float(eff.get("rychlost", 5))))
    except (TypeError, ValueError):
        speed = 5.0
    if typ == "barva":
        keys = {"typ": "barva", "barva": first, "jas": jas}
    elif typ == "vlastni":
        keys = {"typ": "barva", "barva": eff.get("zaklad", first), "jas": jas}
    elif typ == "dychani":
        keys = {"typ": "dychani", "barva": first, "perioda_s": round(15 / speed, 1), "jas": jas}
    else:
        keys = {"typ": "cyklus", "perioda_s": round(25 / speed, 1), "jas": jas}
    return keys, dict(keys)
