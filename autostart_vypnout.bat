@echo off
rem Plna cesta - nezavisi na systemove promenne PATH
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0autostart.ps1" -Vypnout
