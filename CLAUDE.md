# RGB-LCD – ovládání NZXT Krakenu, chlazení a RGB bez NZXT CAM

## Komunikace s uživatelem
- Odpovídej vždy česky. Anglické výstupy (chybové hlášky, logy, dokumentace) vždy přelož do češtiny.
- Přesnost před odhadem. Když něco nevíš, řekni to. Odhad vždy označ jako odhad.
- Příkazy pro uživatele piš konkrétně a připravené ke zkopírování (Windows, cmd/PowerShell).
- Zdrojem pravdy je kód v tomto adresáři. Tento soubor popisuje stav z předchozí práce v claude.ai – pokud se s kódem rozchází, věř kódu a upozorni na rozdíl.

## Cíl projektu
Nahradit NZXT CAM vlastní aplikací v Pythonu:
- LCD displej Krakenu s vlastními obrazovkami,
- řízení pumpy a ventilátorů,
- sjednocené ovládání RGB LED (zatím nehotové).
Uživatel preferuje softwarové řešení, žádné hardwarové úpravy.

## Hardware
- Základní deska: Gigabyte B650M Aorus Elite (ARGB hlavičky, Gigabyte RGB Fusion 2.0 5702 Controller, IT5701, FW 4.0.30.2)
- AIO: NZXT Kraken 240 RGB (RL-KR240-B1), FW 2.0.0, LCD 240×240 px, v liquidctl jako „NZXT Kraken 2023“
- NZXT 2023 RGB Controller (FW 1.5.0): kanál led1 a led2 = po jednom F140 RGB Core (8 LED, LED 1 směrem k čelu PC), led3 volný. Rychlost F140 neřídí – F140 jsou zapojené do desky na Systém 1 a Systém 2 (SYS_FAN), na CPU_FAN je tachometr pumpy (odhad podle otáček).
- Gigabyte RGB Fusion 2.0: ventilátory na desce (ne F140, každý 16 LED): na ARGB hlavičce D_LED1 jsou 2 paralelně přes rozbočovač (svítí stejně), na D_LED2 1 samostatně (od 28. 9. 2026, dřív byly všechny 3 na D_LED1). Liquidctl D_LED neovládne, když má hlavička vypnuté vestavěné efekty (přímý režim, nechal tak GCC) – řeší `led.py` vlastními příkazy podle OpenRGB (0x32 maska, 0x58/0x59 barvy po LED, pořadí GRB z kalibrace). Zóna led6 = D_LED1, led7 = D_LED2. LED desky jinak řídí Gigabyte Control Center (GCC, úloha `\GCC`) a přepisuje je – `autostart_zapnout.bat` GCC vypíná. `initialize()` občas napoprvé vrátí nesmysl (AssertionError) → opakovat.
- CPU Ryzen (teplota rychle kolísá → proto vyhlazování)

## Prostředí
- Windows 11, Python 3.12 v `C:\Users\lukas\AppData\Local\Programs\Python\Python312` (v PATH, funguje i `py`)
- liquidctl 1.16.0, winusbcdc 1.7, Pillow, tkinter
- HWiNFO64 se zapnutým Gadget reportingem
- Aplikace: `C:\RGB-LCD\`

## Struktura aplikace
- `rgb_lcd.py` – hlavní smyčka: sběr dat, rotace obrazovek, odesílání na LCD, zápis `stav.json`, log `rgb_lcd.log`
- `kraken.py` – komunikace s Krakenem přes liquidctl (LCD, jas, stav, křivky, fixní výkon)
- `hwinfo.py` – čtení senzorů z HWiNFO; stejný název u více zařízení dostane krátké rozlišení: „Teplota disku (C:)“, „Aktuální rychlost stahování (Wi-Fi 2)“
- `systemdata.py` – hodnoty, které HWiNFO neposílá, přímo z Windows API (ctypes): `@disk C: volno/obsazeno/celkem` (GB, %), `@síť stahování/odesílání` (MB/s, součet i po adaptérech), `@síť rychlost připojení` (Mbps), `@wifi signál` (dBm), `@wifi kvalita` (%), `@wifi rychlost`
- `screens.py` – vykreslování obrazovek Krakenu (Pillow): dva bary, oblouk, budík, dva kruhy, graf, hodiny, dva oblouky (vlevo/vpravo), segmentový prstenec, čtyři hodnoty, chlazení (kapalina + výkon a otáčky pumpy a ventilátorů), graf dvou hodnot, ručičkové hodiny, digitální hodiny se sekundovým prstencem (na řádku / hodiny nad minutami, velikost číslic = „Velikost textu“, datum volitelné), obrázek/logo (`obrazky/kraken/` barevné s průhledným pozadím, `obrazky/` i `obrazky/predlohy/`, úpravy: odstranit pozadí, jen tvar v barvě, černou na bílou). Displej je čtvercový 240×240 (liquidctl `lcd_resolution` pro 0x300E) – obsah se ořízne na obsah a zvětší na celý displej, obrázek delší stranou na celou šířku; náhled v nastavení je čtvercový 1:1.
- `cooling.py` – řízení pumpy a ventilátorů podle teploty CPU, vyhlazení, pojistky
- `ukonceni.py` – zachycení ukončení (zavření okna, Ctrl+Break, odhlášení, vypnutí PC, `WM_CLOSE` od `ukoncit.bat`), aby se stihla nahrát záloha chlazení; jediná instance (mutex `Local\RGB_LCD_dashboard`); skryté okno třídy `RGB_LCD_ukonceni`
- `camservice.py` – zastavení služby CAMService přes Windows API (při startu a když ji něco znovu spustí)
- `autostart.ps1` + `autostart_zapnout.bat` / `autostart_vypnout.bat` – naplánovaná úloha „RGB-LCD“ (při přihlášení, zpoždění 10 s, nejvyšší práva, `pythonw` bez okna) a vypnutí/zapnutí autostartu NZXT CAM (klíč StartupApproved, jako Správce úloh). Soubor .ps1 musí zůstat bez diakritiky (PS 5.1 čte bez BOM jako ANSI).
- `ukoncit.bat` – bezpečné ukončení aplikace běžící na pozadí; `spustit_na_pozadi.bat` – spustí naplánovanou úlohu
- `alphacool.py` – monochromatický Alphacool USB display 240×128 (VID 060C, PID 04EB, T6963): ovladač přes pyusb + libusb-1.0 (`libusb_package`), vlastní vlákno `AlphacoolWorker` (chyba displeje nesmí zdržet chlazení). Protokol podle serdisplib (`serdisp_specific_acoolsdcm.c`). Vyžaduje ovladač WinUSB (Zadig) – původní libusb0 od Alphacoolu má jen 32bitovou DLL.
- `prvky.py` – grafické prvky pro Alphacool (1 bit, bez vyhlazování, „šedá“ = rastr): text, velké číslo, hodiny, bar (plný/segmenty/rysky s maximem/rastr, 2. senzor = rozdělený), sloupce, graf (plocha/sloupce/mřížka), budík, prstenec ze segmentů, tlustý oblouk, ikony 11×11, čára, obdélník. Rozvržení = `config["alphacool"]["prvky"]` (volné x/y/w/h, pořadí = pořadí kreslení). Otočení displeje `otoceni` 0/90/180/270 (90 = namontovaný na výšku otočený doprava); na výšku má vlastní rozvržení 128×240 v `prvky_na_vysku`, kreslí se tak, jak ho uživatel vidí, a pro panel ho otočí `to_panel()`. Písma: rodina/velikost/tučně jen ze složky `fonts/` (`font_index()`, písma Windows se nenabízejí – na 1 bitu jsou nerovná); výchozí Terminus (TTF) v ostré velikosti, drobné popisky Micro 5 (11). Starý pevný přehled (`radky`/`graf`) se při načtení převede (`default_layout`).
- `obrazky/` – obrázky pro prvek „Obrázek“. `obrazky_vytvorit.py` kreslí logo AMD (šipka) a 9700X ručně; `obrazky_z_predloh.py` dělá loga z barevných předloh v `obrazky/predlohy/` (AMD, AMD čtverec, RYZEN, RYZEN 7, NVIDIA, GeForce RTX): `<název>.png` ve stupních šedi pro velikost „přizpůsobit“, `<název>_<výška>.png` hotové 1bitové pro „původní“; pro Kraken barevné `obrazky/kraken/*.png` (RGBA, pozadí průhledné: odznak RYZEN 7, samolepka a foto procesoru 9700X)
- `mono.py` – vstup pro vykreslení Alphacoolu (volá `prvky.render`), náhled v barvách modrého displeje, seznam senzorů grafů pro historii
- `editor_alphacool.py` – editor rozvržení v okně nastavení: náhled 3×, výběr/posun/velikost myší, šipky, seznam prvků, vlastnosti vč. písma
- `led.py` – LED všech ventilátorů ve vlastním vlákně `LedWorker`: efekty počítá aplikace (softwarově) a posílá barvy každé LED přímo – F140 přes NZXT `super-fixed` (kanály led1/led2, 8 LED), ventilátory na desce přes ARGB D_LED1 a D_LED2 (16 LED). Drží spojení otevřená, animace ~30 snímků/s (měřeno ~12 ms na snímek pro všech 5 ventilátorů), statické efekty jen při změně + obnova po 10 s. Nastaví znovu po probuzení PC (skok hodin > 20 s) a po chybě za 30 s. Při ukončení aplikace pošle klidný stav (vlastní barvy LED); při vypnutí PC / odhlášení (`ukonceni.SHUTDOWN`) a při uspání (`WM_POWERBROADCAST` → `ukonceni.on_power` → `blackout()`) LED zhasne – deska drží hlavičku ARGB pod napětím i ve spánku a vypnutém PC, jinak by na ventilátorech zůstal zamrzlý snímek; po probuzení efekty obnoví. Ostatní zóny desky (malé LED, 12V RGB) jen celá zóna přes liquidctl. `config["led"]`: `jas`, `jas_f140`, `jas_deska`, `stejne_pro_vse`, `vlna`, `efekt` / `efekt_f140` / `efekt_deska`, vlastní barvy v `nzxt.led1/led2.barvy` a `argb.D_LED1.barvy`, `argb.*.pouzito`/`pocet_led`. Vestavěné efekty řadičů se nepoužívají (slabý jas, na každém řadiči jiné). Synchronizace: `vlna` False = všechny ventilátory stejná fáze; natočení každého ventilátoru `posun` (LED 1) a `obracene` v `nzxt.led1/led2` a `argb.D_LEDx` (`orientation()`/`_orient()`, neplatí pro vlastní barvy LED; náhled kreslí včetně natočení, LED 1 vpravo po směru hodin).
- `led_efekty.py` – výpočet efektů bez hardwaru (vlákno LED i živý náhled): jedna barva, vlastní barvy LED, duha – točení/přelévání, dýchání, kometa, přechod 2 barev, třpyt, oheň, blikání, paleta a výseče – točení, dvojitá kometa, stírání barev, polární záře, plazma, duhový třpyt, tep srdce, stroboskop, policie, podle teploty (senzor, vyhlazení 2 s); jas kvadraticky (vnímaný)
- `editor_led.py` – stránka LED: jas + vyrovnání skupin, efekt (společný / zvlášť F140 a deska, vlna), vlastní barvy (kruh 8 / 16 LED), živý animovaný náhled, sbalené nastavení hardwaru (ARGB hlavičky, další zóny desky)
- `config.py` – výchozí nastavení, načítání/ukládání, migrace starého formátu
- `config.json` – uživatelské nastavení (změny se načtou za běhu podle mtime, bez restartu)
- `nastaveni.py` – okno nastavení (tkinter): postranní navigace se 4 stránkami (Kraken LCD – obrazovky, editor, živý náhled 240×240 1:1, obecné; Chlazení – dlaždice stavu, graf a body křivek; LED; Alphacool), nahoře Uložit / Vrátit uložené a hlášení neuložených změn
- `vzhled.py` – tmavý vzhled okna nastavení podle návrhu z Claude Design (https://claude.ai/artifact/VfhrwLMbyGrLZUuKCuCYpB): barvy, písma (Segoe UI, Consolas), styly ttk na základu „clam“, pomocné prvky (karta, posuvník, přepínač v řadě, barevné tlačítko, rolovací panel `ScrollFrame`)
- `stav.json` – živá data pro okno nastavení
- `fonts/` – Montserrat (Light, SemiBold, Bold, ExtraBold, Black) pro Kraken; pixelová písma pro Alphacool z Google Fonts (licence OFL, `OFL-*.txt`): Silkscreen (8/16 px, jen velká písmena, CHYBÍ ě č ř ů ď ť ň), Press Start 2P (8/16/24), VT323 (16/32), Tiny5 (10); s češtinou: Departure Mono (11), Terminus TTF (12/14/16/…, i tučné; 12 = verzálky 8 px), Pixelify Sans, Jersey 10 (20), Micro 5 (11, nejmenší), Pixel Operator (16, i tučné; varianty 8 / HB 8 / Mono 8 mají háčky jen částečně, licence CC0); bez češtiny Spleen 5×8 (`.otb`, jen 8 px, BSD) – pixelová písma jsou ostrá jen v násobcích nativní velikosti; bitmapové `.otb` se v jiné velikosti vykreslí ve své
- `spustit.bat`, `nastaveni.bat`

## Vyřešené problémy – neřeš znovu
- CAM a liquidctl kolidují. Služba `CAMService` drží rozhraní displeje i při zavřeném CAM → nutné `Stop-Service CAMService` (vyžaduje práva správce).
- winusbcdc 1.7 bez zadaného VID/PID nevrátí žádná rozhraní → volat s `vid=0x1E71, pid=0x300E`.
- Kraken 2023 se registruje pod GUID `{300e300d-7EE7-1125-0724-101503010819}`, ne pod standardním GUID, který hledá liquidctl.
- Rozhraní displeje (Interface 0, třída USBDevice) má WinUSB nativně – Zadig není potřeba.
- Přenos obrázku na LCD trvá 30–80 ms. Obrázek se posílá jen při změně; hodnoty se obnovují každou sekundu, obrazovky se střídají po 5 s.
- Grafika se kreslí ve 3× rozlišení (720×720), Lanczos downsampling, ořez na obsah a roztažení na celý displej.
- Jas LCD je na 100 %, víc hardwarově nejde. Jas grafiky řeší tučnější písmo, silnější prvky a gama grafiky (výchozí 0.65).
- HWiNFO data z registru `HKCU\Software\HWiNFO64\VSB`. Názvy senzorů jsou česky: „CPU (Tctl/Tdie)“, „Teplota GPU“, „Takt jader“ (MHz), „Takt GPU“.
- Senzor, u kterého je v HWiNFO zaškrtnuté „Report value in Gadget“, se automaticky přidá jako obrazovka s obloukem.
- Interní zdroje dat z Krakenu: `@kapalina`, `@pumpa`, `@pumpa_vykon`, `@ventilatory`, `@ventilatory_vykon`.
- Posuvník „Velikost textu“ (0,7–1,4) mění text vůči barům; hodiny řídí jen „Velikost obsahu“.

## Chlazení – BEZPEČNOST MÁ PŘEDNOST
- Kraken sám umí řídit jen podle teploty kapaliny. V režimu CPU proto aplikace každou sekundu vezme teplotu CPU z HWiNFO, zprůměruje ji za 5 s a pošle výkon, pokud se změní alespoň o 2 %.
- Uživatelovy křivky (teplota CPU → výkon):
  - pumpa: 20 % do 75 °C, 45 % při 80 °C, 75 % při 85 °C, 100 % od 90 °C
  - ventilátory: 10 % do 75 °C, 30 % při 80–85 °C, 80 % při 90 °C, 100 % od 95 °C
- Pojistky: záložní křivky podle kapaliny se nahrají do Krakenu (ten se pak řídí sám), když:
  - teplota CPU z HWiNFO chybí déle než 5 s,
  - aplikace končí – Ctrl+C, zavření okna, Ctrl+Break (handler konzole), odhlášení a vypnutí PC (skryté okno, `WM_ENDSESSION`; handler konzole tyto události nedostane, protože Python má načtenou user32.dll),
  - nastane chyba komunikace s Krakenem (před odpojením),
  - řízení je v nastavení vypnuté.
  `Cooling.needs_fallback` je po startu True (Kraken může být na pevném výkonu po pádu předchozí instance) a maže se jen úspěšným nahráním křivek podle kapaliny.
- Bod 100 % od 59 °C kapaliny přidává do každé křivky liquidctl (`_CRITICAL_TEMPERATURE` v kraken3.py), i do „pevného“ výkonu. Pumpa minimum 20 % (kraken.py i liquidctl).
- Nezachytí se: zabití procesu (Správce úloh, `taskkill /F`), pád Pythonu, výpadek proudu. Pak Kraken zůstane na posledním výkonu až do 59 °C kapaliny.
- Nikdy nespouštěj test, který nechá pumpu nebo ventilátory na nízkém fixním výkonu bez pojistky. Před každým testem, který mění chlazení, se uživatele zeptej.

## Co zbývá
1. ~~Ovládání LED~~ – hotovo (`led.py`, záložka LED). Kraken 2023 (PID 0x300E) nemá v liquidctl 1.16 žádné LED kanály. Otevřené: rychlost F140 na SYS_FAN desky – liquidctl ji neumí (BIOS Smart Fan 6, nebo LibreHardwareMonitor + ovladač jádra).
2. ~~Automatické spuštění po startu Windows~~ – hotovo (`autostart_zapnout.bat`). Bez ikony v liště jde aplikaci ukončit jen přes `ukoncit.bat` (zabití ve Správci úloh přeskočí zálohu chlazení!).
3. **Ikona v systémové liště.**

## Pracovní postup
- Před většími změnami udělej git commit. (Git zatím není nainstalovaný – do té doby záloha souborů.)
- Běžící aplikace drží USB zařízení – před testy přes liquidctl ji ukonči.
- Po změnách ověř syntaxi (`py -m py_compile`) a zkontroluj `rgb_lcd.log`.
