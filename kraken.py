# kraken.py - pripojeni k NZXT Kraken 2023 (fw 2.x) ve Windows a posilani obrazku
# Obsahuje dve opravy oproti liquidctl 1.16 + winusbcdc 1.7:
#   1) spravny GUID rozhrani displeje {300e300d-7EE7-1125-0724-101503010819}
#   2) hledani rozhrani s VID/PID (bez nich winusbcdc 1.7 nevrati nic)

import io
from winusbcdc.winusbpy import WinUsbPy
from winusbcdc.winusbclasses import GUID

VID, PID = 0x1E71, 0x300E

_B = WinUsbPy.byte_array
WinUsbPy.usb_winusb_guid = GUID(
    0x300E300D, 0x7EE7, 0x1125, _B(0x07, 0x24, 0x10, 0x15, 0x03, 0x01, 0x08, 0x19)
)

from liquidctl import find_liquidctl_devices  # noqa: E402  (az po oprave GUID)


class Kraken:
    def __init__(self, brightness=100, double_send=False):
        self.brightness = brightness
        self.double_send = double_send
        self.dev = None
        self._first = True

    def open(self):
        paths = WinUsbPy.list_usb_devices(
            deviceinterface=True, present=True, findparent=True, vid=VID, pid=PID
        )
        if not paths:
            raise RuntimeError("Rozhrani displeje Krakenu nenalezeno.")

        dev = next((d for d in find_liquidctl_devices() if "Kraken" in d.description), None)
        if dev is None:
            raise RuntimeError("Kraken nenalezen.")

        dev.connect()
        try:
            if not dev.bulk_device:
                bulk = WinUsbPy()
                if not bulk.init_winusb_device_with_path(paths[0].path):
                    raise RuntimeError(
                        "Rozhrani displeje drzi jiny program (nejspis NZXT CAM / CAMService)."
                    )
                dev.bulk_device = bulk
            dev.initialize()
            dev.set_screen("lcd", "brightness", str(self.brightness))
        except Exception:
            dev.disconnect()
            raise
        self.dev = dev
        self._first = True

    def set_brightness(self, value):
        self.brightness = int(value)
        self.dev.set_screen("lcd", "brightness", str(self.brightness))

    def status(self):
        """Stav Krakenu: teplota kapaliny, otacky a vykon pumpy a ventilatoru."""
        names = {"liquid temperature": ("@kapalina", "°C"), "pump speed": ("@pumpa", "RPM"),
                 "pump duty": ("@pumpa_vykon", "%"), "fan speed": ("@ventilatory", "RPM"),
                 "fan duty": ("@ventilatory_vykon", "%")}
        out = {}
        for key, value, _unit in self.dev.get_status():
            m = names.get(key.lower())
            if m:
                out[m[0]] = {"value": float(value), "unit": m[1], "sensor": "Kraken"}
        return out

    def liquid_temp(self):
        item = self.status().get("@kapalina")
        return item["value"] if item else None

    def set_fixed(self, channel, duty):
        """Pevny vykon (0-100 %). Pojistka ve firmwaru zustava: od 59 °C kapaliny 100 %."""
        if channel == "pump":
            duty = max(20, duty)
        self.dev.set_fixed_speed(channel, int(round(max(0, min(100, duty)))))

    def apply_cooling(self, cooling):
        """Nahraje krivky pumpy a ventilatoru do Krakenu. Kraken je pak ridi sam podle
        teploty kapaliny - funguje i kdyz aplikace nebezi. Nad 59 °C jede vse na 100 %."""
        for channel, key in (("pump", "pumpa"), ("fan", "ventilatory")):
            points = [(int(t), int(d)) for t, d in cooling.get(key, [])]
            if points:
                self.dev.set_speed_profile(channel, sorted(points))

    def show(self, img):
        buf = io.BytesIO()
        img.save(buf, "PNG")
        buf.seek(0)
        if self._first or self.double_send:
            # prvni obrazek po inicializaci musi jit dvakrat - to dela set_screen
            self.dev.set_screen("lcd", "static", buf)
            self._first = False
        else:
            data = self.dev._prepare_static_file_rgb16(buf, self.dev.orientation)
            self.dev._send_2023_data_fw2(
                data, [0x06, 0x00, 0x00, 0x00] + list(len(data).to_bytes(4, "little"))
            )

    def close(self, back_to_liquid=True):
        if self.dev is None:
            return
        try:
            if back_to_liquid:
                self.dev.set_screen("lcd", "liquid", None)
        except Exception:
            pass
        try:
            if self.dev.bulk_device:
                self.dev.bulk_device.close_winusb_device()
        except Exception:
            pass
        try:
            self.dev.disconnect()
        except Exception:
            pass
        self.dev = None
