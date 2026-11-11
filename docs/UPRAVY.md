# Úprava aplikace pro vlastní sestavu

RGB-LCD vzniklo pro jeden konkrétní počítač (viz [README](../README.md#hardware-na-kterém-to-běží)).
Tenhle návod popisuje, co jde změnit jen v okně nastavení, co znamená úpravu kódu
a kde v kódu ta místa jsou.

> **Chlazení má přednost.** Kraken po připojení řídí pumpu a ventilátory podle křivek
> z aplikace. Než budeš měnit cokoli kolem Krakenu nebo `cooling.py`, přečti si
> [Chlazení a bezpečnost](#chlazení-a-bezpečnost). Nikdy netestuj tak, že pumpa nebo
> ventilátory zůstanou na nízkém pevném výkonu bez pojistky.

## Obsah

1. [Než začneš](#než-začneš)
2. [Co jde vypnout bez úprav kódu](#co-jde-vypnout-bez-úprav-kódu)
3. [Odstranění nepoužívaných částí z kódu](#odstranění-nepoužívaných-částí-z-kódu)
4. [Ventilátory na desce (ARGB)](#ventilátory-na-desce-argb)
5. [Ventilátory NZXT (RGB Controller)](#ventilátory-nzxt-rgb-controller)
6. [Rozmístění ve skříni (vlna a prostorové efekty)](#rozmístění-ve-skříni)
7. [Jiná grafická karta](#jiná-grafická-karta)
8. [Jiná deska, jiný Kraken, jiný hardware](#jiná-deska-jiný-kraken-jiný-hardware)
9. [Senzory a teploty](#senzory-a-teploty)
10. [Chlazení a bezpečnost](#chlazení-a-bezpečnost)
11. [Jak změny vyzkoušet](#jak-změny-vyzkoušet)

---

## Než začneš

- **Nastavení vs. kód.** Všechno, co jde nastavit v okně (`nastaveni.bat`), se ukládá do
  `config.json` a běžící aplikace si ho načte sama do pár sekund. Úprava kódu (`*.py`)
  vyžaduje restart aplikace – tlačítko **Restartovat aplikaci** vlevo dole v okně
  (okno samo pozná, že na pozadí běží starší verze kódu).
- `config.json` v repozitáři je nastavení autora. Když ho smažeš, aplikace začne
  s výchozím nastavením z `config.py` (a `led.default_config()`).
- Složka aplikace může být kdekoli.
- Chybějící zařízení aplikaci neshodí: každé zařízení (NZXT RGB Controller, deska,
  grafika, klávesnice, Alphacool, Spotify) se ohlásí jako nenalezené a zkouší se znovu
  po chvíli (10–30 s). Kraken je výjimka – na něm stojí LCD i chlazení, bez něj nemá
  hlavní smyčka smysl.
- Před úpravou kódu si udělej zálohu (`git commit`), ať se máš kam vrátit.

## Co jde vypnout bez úprav kódu

| Co | Kde v okně |
|---|---|
| Řízení LED úplně | **LED ventilátorů** → nahoře „Řídit LED z aplikace“ |
| Grafická karta | **LED ventilátorů** → záložka *Další zařízení* → karta grafiky, „zapnuto“ |
| Hlavička ARGB, kterou nepoužíváš | **LED ventilátorů** → *Zapojení* → ARGB hlavičky, „použito“ |
| Další zóny desky (malé LED, 12V RGB) | **LED ventilátorů** → *Další zařízení* → zóny desky, režim „vypnuto“ |
| Hudba ze Spotify (LED) | **LED ventilátorů** → *Hudba* → „Když hraje Spotify, přepnout na hudební vizualizér“ |
| Obrazovka „Právě hraje“ na LCD | **Kraken LCD** → karta „Právě hraje (Spotify)“ |
| Ikona spuštěné hry na LCD | **Kraken LCD** → karta „Ikona spuštěného programu“ |
| Klávesnice | **Klávesnice** → „Řídit podsvícení z aplikace“ |
| Alphacool displej | **Alphacool LCD** → „Zobrazovat na displeji“ |
| Řízení chlazení podle CPU | **Chlazení** → „Řídit pumpu a ventilátory“ (vypnuto = Kraken se řídí sám podle kapaliny) |
| Obrazovky na Krakenu | **Kraken LCD** → seznam obrazovek, „Zapnout / vypnout“ nebo „Odebrat“ |

## Odstranění nepoužívaných částí z kódu

Většinou stačí část vypnout v okně (viz výše). Když ji chceš z okna i z běhu úplně pryč:

### Klávesnice Logitech G815

V `led.py` nastav:

```python
KEYBOARD = False             # klavesnice G815 (False = skryta v okne i ve vlakne)
```

Zmizí stránka *Klávesnice* v okně a vlákno LED klávesnici nehledá. Soubory
`klavesnice*.py`, `klavesy_g.py`, `klavesy_stisk.py`, `hlasitost.py` a
`editor_klavesnice.py` pak můžeš nechat (importují se, ale nic nedělají), nebo je smazat
spolu s importy v `led.py`, `config.py`, `nastaveni.py` – to už je větší zásah, po něm
vždy ověř, že aplikace naběhne (viz [Jak změny vyzkoušet](#jak-změny-vyzkoušet)).

Jinou klávesnici Logitech kód neumí: rozložení kláves (`klavesnice_rozlozeni.py`) i čísla
funkcí HID++ jsou pro G815. Jiný model by potřeboval vlastní mapu kláves.

### Alphacool displej

Chybějící displej aplikaci nevadí (vlákno `AlphacoolWorker` ho jen občas hledá znovu);
v okně ho vypneš volbou „Zobrazovat na displeji“. Kdo chce i stránku v okně pryč, smaže položku `("alpha", …)`
ze seznamu `PAGES` v `nastaveni.py`. Vlákno se spouští v `rgb_lcd.py` (`AlphacoolWorker()`).

### Spotify

Balíčky `numpy` a `winrt-*` se v kódu načítají, až když jsou potřeba, takže bez nich by
aplikace měla naběhnout jen bez hudby (podle kódu, nevyzkoušeno). Vizualizér vypneš v okně. Jiný
přehrávač než Spotify: `hudba.py`, konstanty `PLAYER_APP` (text v AppUserModelId relace
přehrávače ve Windows) a `PLAYER_EXE` (proces, jehož zvuk se zachytává). Vyzkoušené je
jen Spotify.

### Grafická karta

Nepodporovaná karta se prostě nenajde (`grafika.py`, `SUPPORTED`) a v okně se ukáže
chyba – stačí ji vypnout. Viz [Jiná grafická karta](#jiná-grafická-karta).

## Ventilátory na desce (ARGB)

Ventilátory zapojené do ARGB hlaviček desky Gigabyte (D_LED1, D_LED2).

### Jiný počet LED na ventilátoru

V okně: **LED ventilátorů** → *Zapojení* → ARGB hlavičky → **počet LED** (nejvýš 32 na
hlavičku, `ARGB_MAX_LEDS`). Výchozí hodnota pro nové nastavení je `ARGB_FAN_LEDS` v
`led.py` (14).

Jak zjistit správný počet: v *Zapojení* spusť **Test natočení** („obíhá“) – jedna LED
obíhá dokola. Když na kousku kruhu nesvítí nic, je počet moc velký; když LED přeskočí
dřív, než oběhne celý kruh, je moc malý.

### Víc ventilátorů na jedné hlavičce

- **Paralelně přes rozbočovač** (Y kabel): všechny svítí stejně, v aplikaci je to jeden
  ventilátor. Počet LED nastav podle jednoho ventilátoru. Nic dalšího není potřeba.
- **Za sebou (daisy chain)**: LED jdou za sebou, takže nastav součet LED všech
  ventilátorů (např. 3 × 8 = 24). Efekty pak počítají s jedním velkým kruhem – na
  každém ventilátoru bude jen část efektu. Rozdělení na samostatné ventilátory kód zatím
  neumí (musel by se v `led.targets()` jeden cíl rozdělit na několik a při odeslání
  zase spojit za sebe).

### Další hlavička (D_LED3 …)

Hlavičky jsou v `led.py`:

```python
# ARGB hlavicky desky: nazev -> (zona liquidctl, prikaz pro barvy po LED, bit masky 0x32)
ARGB_HEADERS = {"D_LED1": ("led6", 0x58, 0x01), "D_LED2": ("led7", 0x59, 0x02)}
```

Deska B650M Aorus Elite má jen dvě. Na desce s víc hlavičkami by se přidal další záznam,
ale **zónu, příkaz i bit masky je nutné zjistit pro konkrétní řadič** (zdroj:
[OpenRGB](https://gitlab.com/CalcProgrammer1/OpenRGB), ovladač *GigabyteRGBFusion2USB*).
Navíc maska přímého režimu `0x03` (= D_LED1 + D_LED2) je v `led.py` zapsaná přímo na
několika místech (`send_feature_report([0xCC, 0x32, 0x03] …)`) a musela by obsahovat
i nový bit. Pak ještě doplnit názvy v `editor_led.py` (`FAN_NAMES`), barvu testu
(`TEST_COLORS`) a polohu ve skříni (viz [Rozmístění ve skříni](#rozmístění-ve-skříni)).
Neověřené – posílat do řadiče příkazy podle odhadu nedoporučuju.

## Ventilátory NZXT (RGB Controller)

Ventilátory F140 RGB Core na NZXT RGB Controller 2023 (kanály led1, led2; led3 je volný).

- **Jiné ventilátory NZXT se stejným počtem LED (8)**: bez úprav, jen názvy v okně
  (`editor_led.py`, `FAN_NAMES`).
- **Jiný počet LED**: `LEDS_PER_FAN` v `led.py` (platí pro všechny kanály NZXT).
- **Třetí kanál (led3)**: kód počítá pevně se dvěma ventilátory `f140_1` a `f140_2`.
  Bylo by potřeba:
  1. `led.targets()` – přidat `("f140_3", LEDS_PER_FAN, "f140", barvy)`,
  2. `Session.send()` v `led.py` – poslat `set_color("led3", "super-fixed", …)`
     (pozor: když jsou všechny kanály stejné, posílá se jednou přes `"sync"`),
  3. `wave_offsets()`, `case_points()` a `CASE_LAYOUT` – zařadit ho do skříně,
  4. `TEST_COLORS` a názvy v `editor_led.py` (`FAN_NAMES` a další slovníky s `f140_2`).
  Hledej v kódu `f140_2` – všechna místa, kde se s druhým F140 počítá, potřebují i třetí.
- **Jiný řadič NZXT** (Smart Device V2, RGB & Fan Controller…): řadič se hledá podle
  názvu v liquidctl v `led._devices()` (`"NZXT 2023 RGB" in d.description`). Jiný model
  by mohl fungovat po úpravě názvu, pokud ho liquidctl podporuje s režimem `super-fixed`
  – neověřené.

## Rozmístění ve skříni

Efekt „vlna“ a prostorové styly hudby počítají s tím, kde ventilátory ve skříni jsou.
Obojí je v `led.py`:

```python
# poradi vlny zepredu dozadu (grafika na konci = vlna obehne skrin dokola)
CASE_ORDER = ("D_LED1", "F140", "D_LED2", "grafika")

# poloha ve skrini: x 0 = predek .. 1 = zadek, y 0 = nahore .. 1 = dole
# (stred x, stred y, polomer x, polomer y, druh)
CASE_LAYOUT = {
    "D_LED1": (0.08, 0.36, 0.01, 0.17, "svisle"),          # predni ventilator
    "f140_predni": (0.38, 0.10, 0.14, 0.0, "vodorovne"),   # F140 na strope
    "f140_zadni": (0.67, 0.10, 0.14, 0.0, "vodorovne"),
    "D_LED2": (0.90, 0.36, -0.05, 0.17, "svisle"),         # zadni (zaporny polomer x = zrcadlove)
    "grafika": (0.58, 0.80, 0.0, 0.0, "bod"),
}
```

- `svisle` = ventilátor ve svislé stěně (přední, zadní, boční), `vodorovne` = leží na
  stropě nebo na dně, `bod` = jedna LED (pásek grafiky).
- Nejjednodušší je vyfotit skříň z boku a odečíst polohy jako podíl šířky a výšky fotky.
- Který F140 je blíž předku a natočení každého ventilátoru (kde je LED 1, směr) se
  nastavuje v okně: *Zapojení* → **Natočení ventilátorů** + **Test** („spodek“, „obíhá“,
  „F140 předek“).
- Živý náhled „Jako ve skříni“ na stránce LED ukazuje, jak aplikace rozmístění vidí.

## Jiná grafická karta

Podporovaná karta je v `grafika.py`:

```python
SUPPORTED = {(0x2F0410DE, 0x417D1458): ("RTX 5070 Eagle OC", 0x75)}
#            (PCI ID karty, subsystém): (název, adresa řadiče LED na I2C)
```

Řadič LED karet Gigabyte řady RTX 50 (protokol *GigabyteRGBFusion2BlackwellGPUController*
z OpenRGB) mají i jiné karty Gigabyte. Novou kartu přidávej **jen když ji OpenRGB uvádí
se stejným ovladačem a adresou** – na sběrnici I2C karty jsou i jiné čipy a zápis na
špatnou adresu může nadělat škodu. PCI ID a subsystém zjistíš ve Správci zařízení
(karta → Vlastnosti → Podrobnosti → ID hardwaru: `VEN_10DE&DEV_2F04&SUBSYS_417D1458`).

Ruční test barvy: `py grafika.py ff0000`.

Karty jiných výrobců (ASUS, MSI…) mají úplně jiné řadiče – potřebovaly by nový modul.

## Jiná deska, jiný Kraken, jiný hardware

- **Jiná deska Gigabyte s RGB Fusion 2.0** (řadič IT5701 / IT5702): pravděpodobně půjde,
  ale ARGB hlavičky a zóny se mohou lišit (viz [Další hlavička](#další-hlavička-d_led3-)).
  Řadič se hledá v `led._devices()` podle `"Fusion"` v názvu zařízení liquidctl. Odhad,
  neověřené.
- **Deska jiného výrobce** (ASUS Aura, MSI Mystic Light…): kód ji neumí, potřebovala by
  vlastní ovladač místo části „fusion“ v `led.py`.
- **Jiný Kraken**: `kraken.py` je psaný pro Kraken 2023 (`PID 0x300E`, firmware 2.x)
  včetně opravy GUID, pod kterým se ve Windows registruje. Kraken Elite / 2024 má jiné
  PID a větší displej (obrazovky se kreslí pro 240 × 240, `screens.SIZE`). Starší Krakeny
  (X53/X63/X73, Z) mají jiný protokol displeje. Úprava je možná, ale je to práce
  s ověřováním na skutečném zařízení.
- **Jiný procesor nebo grafika** pro teploty: stačí jiné senzory, viz níže.

## Senzory a teploty

- Teploty a další hodnoty bere aplikace z [HWiNFO64](https://www.hwinfo.com/) – v HWiNFO
  zapni *Settings → HWiNFO Gadget* a u senzorů, které chceš, zaškrtni **Report value
  in Gadget**.
- Názvy senzorů jsou takové, jak je ukazuje HWiNFO – autor má HWiNFO česky („CPU
  (Tctl/Tdie)“, „Teplota GPU“). V jiném jazyce nebo s jiným procesorem (Intel: „CPU
  Package“) vyber senzory znovu: na obrazovkách v okně **Kraken LCD** a pro chlazení
  v **Chlazení** → **Senzor CPU**.
- Ukázková data a výchozí senzory nových obrazovek jsou v `kraken_prvky.py` (`CPU`,
  `GPU`, `RAM`, `SAMPLES`) a `nastaveni.py`.

## Chlazení a bezpečnost

- Křivky pumpy a ventilátorů se nastavují v okně **Chlazení** (body teplota → výkon)
  a jsou ve `config.json` (`chlazeni.cpu` = podle CPU, `chlazeni.pumpa` /
  `chlazeni.ventilatory` = záložní podle kapaliny, ty se nahrají do Krakenu při každém
  problému).
- **Záložní křivky podle kapaliny nikdy nenastavuj nízko** – platí, když aplikace
  spadne, HWiNFO zamrzne nebo se aplikace ukončí. Kraken navíc sám dává 100 % od 59 °C
  kapaliny (přidává liquidctl) a pumpa nejde pod 20 %.
- Aplikaci ukončuj přes `ukoncit.bat` nebo tlačítko v okně. Zabití procesu (Správce
  úloh, `taskkill /F`) přeskočí nahrání záložních křivek – Kraken pak zůstane na
  posledním výkonu.
- Pojistky jsou v `cooling.py` (`MISSING_LIMIT_S` = jak dlouho smí teplota chybět,
  `STALE_LIMIT_S` = jak dlouho se smí neměnit). Neprodlužuj je.
- Rychlost ventilátorů zapojených do desky (SYS_FAN) aplikace neřídí – řídí je BIOS
  desky. Aplikace řídí jen pumpu a ventilátory připojené přímo ke Krakenu.

## Jak změny vyzkoušet

1. Ukonči aplikaci na pozadí (drží USB zařízení):

   ```bat
   ukoncit.bat
   ```

2. Ověř, že kód jde přeložit:

   ```bat
   py -m py_compile rgb_lcd.py led.py nastaveni.py
   ```

3. Spusť aplikaci v okně konzole – chyby uvidíš hned:

   ```bat
   spustit.bat
   ```

4. Podívej se do logu `rgb_lcd.log` (ve složce aplikace): připojení zařízení, chyby,
   co se nenašlo.
5. Okno nastavení (`nastaveni.bat`) ukáže stav LED, chlazení a zařízení.
6. Když vše běží, vrať aplikaci na pozadí: `spustit_na_pozadi.bat` (pokud máš zapnutý
   autostart přes `autostart_zapnout.bat`).
