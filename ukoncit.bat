@echo off
rem Bezpecne ukonceni aplikace bezici na pozadi - chlazeni prevezme Kraken (krivky podle kapaliny)
cd /d "%~dp0"
py ukonceni.py --ukoncit
"%SystemRoot%\System32\timeout.exe" /t 4 >nul
