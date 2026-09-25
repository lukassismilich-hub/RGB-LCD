# test_lcd.py - test nahrani obrazku na NZXT Kraken 2023 (firmware 2.x) ve Windows
# Pouziti:  py test_lcd.py            (posle C:\RGB-LCD\test.png)
#           py test_lcd.py cesta.png  (posle jiny obrazek 240x240)
# NZXT CAM i sluzba CAMService musi byt zastavene.

import sys
from winusbcdc.winusbpy import WinUsbPy
from winusbcdc.winusbclasses import GUID

VID, PID = 0x1E71, 0x300E

# 1) Kraken 2023 se hlasi pod jinym GUID, nez ktery pouziva liquidctl
B = WinUsbPy.byte_array
WinUsbPy.usb_winusb_guid = GUID(
    0x300E300D, 0x7EE7, 0x1125, B(0x07, 0x24, 0x10, 0x15, 0x03, 0x01, 0x08, 0x19)
)

# 2) winusbcdc 1.7 bez zadaneho VID/PID nevrati nic -> hledame s VID/PID
nalezene = WinUsbPy.list_usb_devices(
    deviceinterface=True, present=True, findparent=True, vid=VID, pid=PID
)
print("Rozhrani viditelna pres WinUSB:")
for d in nalezene:
    print("  ", d.path, "|", d.parent)
if not nalezene:
    sys.exit("Rozhrani pro obrazky nenalezeno.")

from liquidctl import find_liquidctl_devices

obrazek = sys.argv[1] if len(sys.argv) > 1 else r"C:\RGB-LCD\test.png"

for dev in find_liquidctl_devices():
    if "Kraken" not in dev.description:
        continue
    with dev.connect():
        print("Nalezeno:", dev.description)
        if not dev.bulk_device:
            bulk = WinUsbPy()
            if not bulk.init_winusb_device_with_path(nalezene[0].path):
                sys.exit("Rozhrani nejde otevrit - drzi ho jiny program (nejspis CAMService).")
            dev.bulk_device = bulk
        print("Bulk rozhrani: ANO")
        dev.initialize()
        dev.set_screen("lcd", "brightness", "100")
        dev.set_screen("lcd", "static", obrazek)
        print("Hotovo - obrazek odeslan.")
