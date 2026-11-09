# klavesnice_rozlozeni.py - rozlozeni klavesnice Logitech G815 pro efekty po klavesach a nahled
#
# Zona HID++ 0x8081 = cislo LED klavesy. Hypoteza (overuje se testem s uzivatelem): zona = kod HID
# usage - 3 pro bezne klavesy (A = 0x04 -> 1 ... Menu = 0x65 -> 98), modifikatory 0xE0-0xE7 -> 104-111;
# 153 jas, 155-158 multimedia, 180-184 G1-G5, 210 logo (z bitove mapy getInfo).
# Souradnice v jednotkach klavesy "u" (1u = sirka bezne klavesy): x zleva, y shora, sirka, vyska.
# KEYS = [(zona, nazev, x, y, w, h)]. ISO (ceska / evropska) a ANSI (US) se lisi kolem Enteru a leveho Shiftu.

GX = 0.0          # sloupec G-klaves
MX = 1.5          # hlavni blok
NX = 17.0         # sipky a navigace
PX = 20.5         # numericka cast
TOP = 1.2         # pruh nahore (logo, jas, multimedia)


def L(c):
    """Zona pismene (A = 1 ... Z = 26)."""
    return ord(c) - ord("A") + 1


def _row(y, x0, keys):
    out, x = [], x0
    for k in keys:
        if k is None:
            x += 0.5
            continue
        zone, name, w = k if len(k) == 3 else (*k, 1.0)
        out.append((zone, name, x, y, w, 1.0))
        x += w
    return out


def _letters(s):
    return [(L(c), c) for c in s]


def _build(iso=True):
    k = []
    # pruh nahore
    k.append((210, "logo", MX, 0.1, 1.0, 0.9))
    k.append((153, "jas", NX + 2.0, 0.15, 1.0, 0.8))
    for i, (z, n) in enumerate(((158, "předchozí"), (155, "přehrát"), (157, "další"), (156, "ztlumit"))):
        k.append((z, n, PX + i, 0.15, 1.0, 0.8))
    y = TOP
    # G-klavesy
    for i in range(5):
        k.append((180 + i, f"G{i + 1}", GX, y + 1.25 + i, 1.0, 1.0))
    # radek F
    k += _row(y, MX, [(38, "Esc"), None, None] + [(55 + i, f"F{i + 1}") for i in range(4)] + [None]
              + [(59 + i, f"F{i + 5}") for i in range(4)] + [None] + [(63 + i, f"F{i + 9}") for i in range(4)])
    k += _row(y, NX, [(67, "PrtSc"), (68, "ScrLk"), (69, "Pause")])
    # cisla
    y += 1.25
    k += _row(y, MX, [(50, "`")] + [(27 + i, str((i + 1) % 10)) for i in range(10)]
              + [(42, "-"), (43, "="), (39, "Backspace", 2.0)])
    k += _row(y, NX, [(70, "Ins"), (71, "Home"), (72, "PgUp")])
    k += _row(y, PX, [(80, "Num"), (81, "/"), (82, "*"), (83, "-")])
    # QWERTY
    y += 1
    k += _row(y, MX, [(40, "Tab", 1.5)] + _letters("QWERTYUIOP") + [(44, "["), (45, "]")]
              + ([] if iso else [(46, "\\", 1.5)]))
    if iso:
        k.append((37, "Enter", MX + 13.75, y, 1.25, 2.0))
    k += _row(y, NX, [(73, "Del"), (74, "End"), (75, "PgDn")])
    k += _row(y, PX, [(92, "7"), (93, "8"), (94, "9")])
    k.append((84, "+", PX + 3, y, 1.0, 2.0))
    # domaci radek
    y += 1
    k += _row(y, MX, [(54, "Caps", 1.75)] + _letters("ASDFGHJKL") + [(48, ";"), (49, "'")]
              + ([(47, "#")] if iso else [(37, "Enter", 2.25)]))
    k += _row(y, PX, [(89, "4"), (90, "5"), (91, "6")])
    # Shift
    y += 1
    k += _row(y, MX, ([(105, "LShift", 1.25), (97, "\\")] if iso else [(105, "LShift", 2.25)])
              + _letters("ZXCVBNM") + [(51, ","), (52, "."), (53, "/"), (109, "RShift", 2.75)])
    k.append((79, "↑", NX + 1, y, 1.0, 1.0))
    k += _row(y, PX, [(86, "1"), (87, "2"), (88, "3")])
    k.append((85, "Enter", PX + 3, y, 1.0, 2.0))
    # spodni radek
    y += 1
    k += _row(y, MX, [(104, "LCtrl", 1.25), (107, "Win", 1.25), (106, "LAlt", 1.25), (41, "mezerník", 6.25),
                      (110, "RAlt", 1.25), (111, "Fn", 1.25), (98, "Menu", 1.25), (108, "RCtrl", 1.25)])
    k += _row(y, NX, [(77, "←"), (78, "↓"), (76, "→")])
    k += _row(y, PX, [(95, "0", 2.0), (96, ",")])
    return k


KEYS = _build(True)
WIDTH = PX + 4.0
HEIGHT = TOP + 6.25
