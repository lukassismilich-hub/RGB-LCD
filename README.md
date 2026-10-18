# RGB-LCD

Vlastní náhrada NZXT CAM v Pythonu pro Windows: LCD displej NZXT Krakenu s vlastními
obrazovkami, řízení pumpy a ventilátorů podle teploty CPU a sjednocené softwarové efekty
RGB LED (ventilátory NZXT, ARGB hlavičky desky Gigabyte, LED pásek grafické karty).
Volitelně i monochromatický displej Alphacool 240×128.

> Projekt je psaný pro jednu konkrétní sestavu (viz níže). Na jiném hardwaru nemusí
> fungovat a protokoly LED desky a grafické karty jsou ověřené jen na uvedených modelech.

## Co umí

- **LCD Krakenu (240×240):** desítky hotových obrazovek (bary, oblouky, budíky, grafy,
  hodiny, chlazení, síť a disky…), plochý nebo plastický (3D) vzhled, editor volného
  rozvržení s prvky a šablonami, ikona právě spuštěné hry nebo programu.
- **Chlazení:** pumpa a ventilátory Krakenu podle teploty CPU z HWiNFO (Kraken sám umí
  jen podle teploty kapaliny), vyhlazení a pojistky – při výpadku dat, zamrznutí HWiNFO,
  chybě komunikace nebo ukončení aplikace se do Krakenu nahrají záložní křivky podle
  kapaliny.
- **LED:** efekty počítá aplikace (~30 snímků/s) a posílá barvy po jednotlivých LED;
  vlna podle rozmístění ventilátorů ve skříni, vlastní barvy, živý náhled. Při uspání
  a vypnutí PC LED zhasnou.
- **Alphacool USB display 240×128:** 1bitové prvky, sci-fi a Star Wars obrazovky, editor.
- **Okno nastavení** (tkinter, tmavý vzhled): změny se načtou za běhu bez restartu.

## Hardware, na kterém to běží

- NZXT Kraken 240 RGB (v liquidctl „NZXT Kraken 2023“, PID 0x300E), FW 2.0.0
- NZXT RGB Controller 2023 + 2× F140 RGB Core
- Gigabyte B650M Aorus Elite (RGB Fusion 2.0, ARGB D_LED1 / D_LED2)
- Gigabyte GeForce RTX 5070 EAGLE OC SFF (LED přes I2C a NvAPI)
- Alphacool USB display 240×128 (volitelně, ovladač WinUSB přes Zadig)

## Požadavky

- Windows 11, Python 3.12
- [HWiNFO64](https://www.hwinfo.com/) se zapnutým *Gadget reportingem* (zdroj teplot)
- Balíčky: `py -m pip install -r requirements.txt`
- NZXT CAM nesmí běžet – aplikace zastavuje službu `CAMService` (potřebuje práva správce)

## Spuštění

Aplikace počítá s umístěním ve složce `C:\RGB-LCD`.

```bat
spustit.bat              rem hlavní smyčka v okně konzole
nastaveni.bat            rem okno nastavení
autostart_zapnout.bat    rem naplánovaná úloha po přihlášení (pythonw, bez okna)
ukoncit.bat              rem bezpečné ukončení aplikace běžící na pozadí
```

Aplikaci na pozadí ukončuj přes `ukoncit.bat` nebo tlačítko v okně nastavení – zabití
procesu ve Správci úloh přeskočí nahrání záložních křivek chlazení.

## Obrázky a loga

Složka `obrazky/` (loga výrobců pro prvek „Obrázek“) není v repozitáři – loga jsou
ochranné známky jejich vlastníků. Vlastní obrázky stačí nakopírovat do `obrazky/`
(barevné s průhledným pozadím pro Kraken do `obrazky/kraken/`).

## Upozornění

Software mění výkon pumpy a ventilátorů a posílá nedokumentované příkazy řadičům LED.
Používáš ho na vlastní nebezpečí. Kraken má vlastní pojistku (100 % od 59 °C kapaliny),
ale ta nenahradí správně nastavené křivky.

## Poděkování

- [liquidctl](https://github.com/liquidctl/liquidctl) – komunikace s Krakenem a řadiči
- [OpenRGB](https://gitlab.com/CalcProgrammer1/OpenRGB) – popis protokolů RGB Fusion 2.0
  a LED grafické karty Gigabyte
- [serdisplib](https://serdisplib.sourceforge.net/) – protokol displeje Alphacool

## Licence

Kód: [GPL-3.0](LICENSE). Písma ve složce `fonts/` mají vlastní licence (SIL OFL, CC0,
BSD) – texty licencí jsou přiložené u nich.
