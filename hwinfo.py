# hwinfo.py - cteni hodnot z HWiNFO pres rozhrani Gadget (registr HKCU\Software\HWiNFO64\VSB)
# Ve free verzi HWiNFO toto rozhrani nevyprsi (na rozdil od Shared Memory).
# Hodnota se objevi, kdyz v HWiNFO u senzoru zaskrtnes "Report value in Gadget".

import re

try:
    import winreg
except ImportError:          # mimo Windows (testy)
    winreg = None

KEY = r"Software\HWiNFO64\VSB"


def _unit_from_text(text):
    """'66.9 °C' -> '°C', '3,808.8 MHz' -> 'MHz', 'Yes' -> ''"""
    parts = str(text).strip().split(" ", 1)
    return parts[1].strip() if len(parts) == 2 else ""


def read_full():
    """Vrati {nazev: {"value": cislo, "unit": jednotka, "sensor": skupina}}.
    Kdyz stejny nazev nese vic skupin, dalsi dostanou do nazvu skupinu v zavorce."""
    if winreg is None:
        return {}
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY)
    except OSError:
        return {}
    raw = {}
    i = 0
    try:
        while True:
            try:
                name, value, _ = winreg.EnumValue(key, i)
            except OSError:
                break
            raw[name] = value
            i += 1
    finally:
        winreg.CloseKey(key)

    items = []
    j = 0
    while f"Label{j}" in raw:
        label = str(raw[f"Label{j}"]).strip()
        sensor = str(raw.get(f"Sensor{j}", "")).strip()
        try:
            val = float(str(raw.get(f"ValueRaw{j}", "")).replace(",", "."))
        except ValueError:
            j += 1
            continue
        items.append((label, sensor, val, _unit_from_text(raw.get(f"Value{j}", ""))))
        j += 1

    counts = {}
    for label, *_ in items:
        counts[label] = counts.get(label, 0) + 1
    out = {}
    for label, sensor, val, unit in items:
        # stejny nazev u vic zarizeni (disky, sitove karty) -> kratke rozliseni v zavorce
        name = label if counts[label] == 1 else f"{label} ({_short(sensor)})"
        if name in out:
            name = f"{label} ({sensor})"
        out[name] = {"value": val, "unit": unit, "sensor": sensor}
    return out


def _short(sensor):
    """'S.M.A.R.T.: WD_BLACK SN770 2TB (...) [D:]' -> 'D:', 'Síť: ... - Wi-Fi 2' -> 'Wi-Fi 2'"""
    m = re.search(r"\[([A-Z]:)\]", sensor)
    if m:
        return m.group(1)
    if " - " in sensor:
        return sensor.rsplit(" - ", 1)[1].strip()
    return sensor


def read():
    """Zjednodusena verze: {nazev: cislo}"""
    return {k: v["value"] for k, v in read_full().items()}
