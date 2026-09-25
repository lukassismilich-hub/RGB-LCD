# hwinfo.py - cteni hodnot z HWiNFO pres rozhrani Gadget (registr HKCU\Software\HWiNFO64\VSB)
# Ve free verzi HWiNFO toto rozhrani nevyprsi (na rozdil od Shared Memory).
# Hodnota se objevi, kdyz v HWiNFO u senzoru zaskrtnes "Report value in Gadget".

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

    out = {}
    j = 0
    while f"Label{j}" in raw:
        label = str(raw[f"Label{j}"]).strip()
        sensor = str(raw.get(f"Sensor{j}", "")).strip()
        try:
            val = float(str(raw.get(f"ValueRaw{j}", "")).replace(",", "."))
        except ValueError:
            j += 1
            continue
        name = label if label not in out else f"{label} ({sensor})"
        out[name] = {"value": val, "unit": _unit_from_text(raw.get(f"Value{j}", "")),
                     "sensor": sensor}
        j += 1
    return out


def read():
    """Zjednodusena verze: {nazev: cislo}"""
    return {k: v["value"] for k, v in read_full().items()}
