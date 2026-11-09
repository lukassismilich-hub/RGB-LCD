@echo off
rem Ukonci zaznam provozu USB (usb_zaznam_start.bat) - spustit jako spravce.
cd /d "%~dp0"
logman stop usbzaznam
logman delete usbzaznam
echo.
if exist usb_zaznam.etl (echo Zaznam ulozen: %~dp0usb_zaznam.etl) else (echo Soubor zaznamu nevznikl.)
pause
