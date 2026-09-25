@echo off
rem Bezpecne ukonceni aplikace bezici na pozadi - chlazeni prevezme Kraken (krivky podle kapaliny)
cd /d "%~dp0"
py ukonceni.py --ukoncit
timeout /t 4 >nul
