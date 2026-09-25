@echo off
rem Spusti aplikaci na pozadi pres naplanovanou ulohu (s pravy spravce, bez dotazu UAC)
"%SystemRoot%\System32\schtasks.exe" /run /tn "RGB-LCD" >nul 2>&1
if errorlevel 1 (
    echo Naplanovana uloha RGB-LCD neexistuje - nejdriv spust autostart_zapnout.bat
    pause
)
