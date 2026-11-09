@echo off
rem Zaznam provozu USB vestavenym nastrojem Windows (logman, bez instalace) - spustit jako spravce.
rem Docasne kvuli zjisteni, jak G HUB uklada rozlozeni klaves do pameti G815; po rozboru smazat.
cd /d "%~dp0"
logman stop usbzaznam -ets >nul 2>&1
logman delete usbzaznam >nul 2>&1
if exist usb_zaznam.etl del usb_zaznam.etl
logman create trace usbzaznam -o "%~dp0usb_zaznam.etl" -nb 128 640 -bs 128 -max 400
logman update trace usbzaznam -p Microsoft-Windows-USB-USBXHCI 0x101
logman update trace usbzaznam -p Microsoft-Windows-USB-UCX 0x101
logman start usbzaznam
echo.
echo Zaznam bezi. Ted v G HUB uloz rozlozeni klaves do pameti klavesnice,
echo pak spust usb_zaznam_stop.bat (taky jako spravce).
pause
