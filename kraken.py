# kraken.py - pripojeni k NZXT Kraken 2023 (fw 2.x) ve Windows a posilani obrazku
# Obsahuje dve opravy oproti liquidctl 1.16 + winusbcdc 1.7:
#   1) spravny GUID rozhrani displeje {300e300d-7EE7-1125-0724-101503010819}
#   2) hledani rozhrani s VID/PID (bez nich winusbcdc 1.7 nevrati nic)

import io
import time

from PIL import Image, ImageChops
from winusbcdc.winusbpy import WinUsbPy
from winusbcdc.winusbclasses import GUID

VID, PID = 0x1E71, 0x300E

_B = WinUsbPy.byte_array
WinUsbPy.usb_winusb_guid = GUID(
    0x300E300D, 0x7EE7, 0x1125, _B(0x07, 0x24, 0x10, 0x15, 0x03, 0x01, 0x08, 0x19)
)

from liquidctl import find_liquidctl_devices  # noqa: E402  (az po oprave GUID)
from liquidctl.error import Timeout  # noqa: E402

# Odpovedi Krakenu na prenos obrazku (fw 2): 37 01 = zacatek prijat, 37 02 = obrazek prijat.
# liquidctl po prikazu cte proste dalsi zpravu HID - ve fronte byvaly stare zpravy (ff 01,
# 75 xx = odpovedi na cteni stavu) a pri startu nekterych her (Diablo IV) se tak ztracela asi
# polovina obrazku. Proto vyprazdnit frontu, cekat na potvrzeni a pri ff / bez odpovedi opakovat.
SEND_TRIES = 3

# RGB565 po bajtech jako liquidctl _prepare_static_file_rgb16 (horni bajt R5 G3, dolni G3 B5),
# ale pres tabulky Pillow misto pythonove smycky pres pixely (0,5 ms misto ~10 ms na snimek)
_HI_R = [(v >> 3) << 3 for v in range(256)]
_HI_G = [v >> 5 for v in range(256)]
_LO_G = [((v >> 2) & 7) << 5 for v in range(256)]
_LO_B = [v >> 3 for v in range(256)]


def rgb565(img, rotation=0):
    """Obrazek -> bajty pro LCD 240x240 (rotation 0-3 = otoceni displeje po 90 stupnich)."""
    im = img.convert("RGB")
    if im.size != (240, 240):
        im = im.resize((240, 240))
    if rotation:
        im = im.rotate(rotation * -90)
    r, g, b = im.split()
    hi = ImageChops.add(r.point(_HI_R), g.point(_HI_G))
    lo = ImageChops.add(g.point(_LO_G), b.point(_LO_B))
    return Image.merge("LA", (hi, lo)).tobytes()


class Kraken:
    def __init__(self, brightness=100, double_send=False):
        self.brightness = brightness
        self.double_send = double_send
        self.dev = None
        self._first = True
        self.rejected = 0                # pocet odmitnutych prenosu obrazku (pro log)

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
        """Poslat obrazek na LCD. True = Kraken ho prijal; False = odmitl i po SEND_TRIES pokusech
        (hlavni smycka ho posle znovu v dalsim kole)."""
        if self._first or self.double_send:
            # prvni obrazek po inicializaci musi jit dvakrat - to dela set_screen
            buf = io.BytesIO()
            img.save(buf, "PNG")
            buf.seek(0)
            self.dev.set_screen("lcd", "static", buf)
            self._first = False
            return True
        data = rgb565(img, self.dev.orientation)
        for _ in range(SEND_TRIES):
            if self._send_fw2(data):
                return True
            self.rejected += 1
            time.sleep(0.03)
        return False

    def _reply(self, want, timeout_s):
        """Pockat na potvrzeni Krakenu (want = 2. bajt: 0x01 zacatek, 0x02 konec prenosu).
        False = odmitnuti (ff xx) nebo nic do timeout_s; zbloudile zpravy (75 xx) preskoci."""
        end = time.monotonic() + timeout_s
        while True:
            left = int((end - time.monotonic()) * 1000)
            if left <= 0:
                return False
            try:
                msg = self.dev.device.read(64, timeout=left)
            except Timeout:
                return False
            if msg[0] == 0x37 and msg[1] == want:
                return True
            if msg[0] == 0xFF:
                return False

    def _send_fw2(self, data):
        """Jako liquidctl _send_2023_data_fw2, ale s kontrolou odpovedi (viz vyse)."""
        dev = self.dev
        dev.device.clear_enqueued_reports()          # zbloudile odpovedi z fronty pryc
        dev._write([0x36, 0x01, 0x00, 0x01, 0x06])  # zacatek prenosu
        if not self._reply(0x01, 0.25):
            return False                             # odmitnuto - data neposilat
        header = [0x12, 0xFA, 0x01, 0xE8, 0xAB, 0xCD, 0xEF, 0x98, 0x76, 0x54, 0x32, 0x10,
                  0x06, 0x00, 0x00, 0x00] + list(len(data).to_bytes(4, "little"))
        dev._bulk_write(header)
        for i in range(0, len(data), dev.bulk_buffer_size):
            dev._bulk_write(data[i:i + dev.bulk_buffer_size])
        dev._write([0x36, 0x02])                     # konec prenosu
        return self._reply(0x02, 0.5)

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
