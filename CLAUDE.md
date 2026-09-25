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
- NZXT 2023 RGB Controller (FW 1.5.0), na něm 2× F140 RGB Core, hlásí 3 ARGB kanály
- CPU Ryzen (teplota rychle kolísá → proto vyhlazování)

## Prostředí
- Windows 11, Python 3.12 v `C:\Users\lukas\AppData\Local\Programs\Python\Python312` (v PATH, funguje i `py`)
- liquidctl 1.16.0, winusbcdc 1.7, Pillow, tkinter
- HWiNFO64 se zapnutým Gadget reportingem
- Aplikace: `C:\RGB-LCD\`

## Struktura aplikace
- `rgb_lcd.py` – hlavní smyčka: sběr dat, rotace obrazovek, odesílání na LCD, zápis `stav.json`, log `rgb_lcd.log`
- `kraken.py` – komunikace s Krakenem přes liquidctl (LCD, jas, stav, křivky, fixní výkon)
- `hwinfo.py` – čtení senzorů z HWiNFO
- `screens.py` – vykreslování obrazovek (Pillow)
- `cooling.py` – řízení pumpy a ventilátorů podle teploty CPU, vyhlazení, pojistky
- `ukonceni.py` – zachycení ukončení (zavření okna, Ctrl+Break, odhlášení, vypnutí PC, `WM_CLOSE` od `ukoncit.bat`), aby se stihla nahrát záloha chlazení; jediná instance (mutex `Local\RGB_LCD_dashboard`); skryté okno třídy `RGB_LCD_ukonceni`
- `camservice.py` – zastavení služby CAMService přes Windows API (při startu a když ji něco znovu spustí)
- `autostart.ps1` + `autostart_zapnout.bat` / `autostart_vypnout.bat` – naplánovaná úloha „RGB-LCD“ (při přihlášení, zpoždění 10 s, nejvyšší práva, `pythonw` bez okna) a vypnutí/zapnutí autostartu NZXT CAM (klíč StartupApproved, jako Správce úloh). Soubor .ps1 musí zůstat bez diakritiky (PS 5.1 čte bez BOM jako ANSI).
- `ukoncit.bat` – bezpečné ukončení aplikace běžící na pozadí; `spustit_na_pozadi.bat` – spustí naplánovanou úlohu
- `config.py` – výchozí nastavení, načítání/ukládání, migrace starého formátu
- `config.json` – uživatelské nastavení (změny se načtou za běhu podle mtime, bez restartu)
- `nastaveni.py` – okno nastavení (tkinter): obrazovky, editor, obecné, živý náhled 240×240, záložka Chlazení
- `stav.json` – živá data pro okno nastavení
- `fonts/` – Montserrat (Light, SemiBold, Bold, ExtraBold, Black)
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
  - ventilátory: 10 % do 75 °C, 30 % při 80–85 °C, 65 % při 90 °C, 100 % od 95 °C
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
1. **Ovládání LED** – F140 RGB Core přes NZXT 2023 RGB Controller (liquidctl: `led1`–`led3`, `sync`), ARGB na desce přes Gigabyte RGB Fusion 2.0 (`led1`–`led8`). Kraken 2023 (PID 0x300E) nemá v liquidctl 1.16 žádné LED kanály (`_COLOR_CHANNELS_KRAKEN2023 = {}`). Cíl: jednotné ovládání z aplikace a okna nastavení.
2. ~~Automatické spuštění po startu Windows~~ – hotovo (`autostart_zapnout.bat`). Bez ikony v liště jde aplikaci ukončit jen přes `ukoncit.bat` (zabití ve Správci úloh přeskočí zálohu chlazení!).
3. **Ikona v systémové liště.**

## Pracovní postup
- Před většími změnami udělej git commit. (Git zatím není nainstalovaný – do té doby záloha souborů.)
- Běžící aplikace drží USB zařízení – před testy přes liquidctl ji ukonči.
- Po změnách ověř syntaxi (`py -m py_compile`) a zkontroluj `rgb_lcd.log`.
