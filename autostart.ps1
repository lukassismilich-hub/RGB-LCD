# autostart.ps1 - automaticke spusteni RGB-LCD po prihlaseni do Windows (bez okna konzole)
#
#   autostart_zapnout.bat  -> naplanovana uloha "RGB-LCD" (pri prihlaseni, nejvyssi prava,
#                             pythonw bez okna) + vypnuti automatickeho spusteni NZXT CAM
#   autostart_vypnout.bat  -> ukonci aplikaci (chlazeni prevezme Kraken), smaze ulohu
#                             a automaticke spusteni NZXT CAM zase zapne
#
# Nejvyssi prava jsou potreba kvuli zastaveni sluzby CAMService. Diky naplanovane uloze
# se pri kazdem startu nepta UAC - jen jednou pri instalaci.
# Soubor je schvalne bez diakritiky (Windows PowerShell 5.1 cte .ps1 bez BOM jako ANSI).

param([switch]$Zapnout, [switch]$Vypnout, [string]$Uzivatel)

$ErrorActionPreference = 'Stop'
$TaskName = 'RGB-LCD'
$App = $PSScriptRoot
$CamRunValue = 'NZXT.CAM'
$RunKey = 'Software\Microsoft\Windows\CurrentVersion\Run'
$ApprovedKey = 'Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run'

if (-not $Zapnout -and -not $Vypnout) {
    Write-Host 'Pouziti: autostart.ps1 -Zapnout | -Vypnout'
    exit 1
}
if (-not $Uzivatel) { $Uzivatel = [Security.Principal.WindowsIdentity]::GetCurrent().Name }

# --- prava spravce (jednou, pres UAC) ---------------------------------------------------
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $mode = if ($Zapnout) { '-Zapnout' } else { '-Vypnout' }
    Write-Host 'Otviram okno s pravy spravce (potvrd dotaz Windows) ...'
    try {
        $p = Start-Process (Join-Path $PSHOME 'powershell.exe') -Verb RunAs -Wait -PassThru -ArgumentList @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"", $mode,
            '-Uzivatel', "`"$Uzivatel`"")
        Write-Host "Okno spravce skoncilo (kod $($p.ExitCode))."
    } catch {
        Write-Host "Okno s pravy spravce se nespustilo: $_" -ForegroundColor Yellow
    }
    # kontrola vysledku z pohledu bezneho uzivatele
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($Zapnout -and $task) { Write-Host "OK: naplanovana uloha '$TaskName' existuje." -ForegroundColor Green }
    elseif ($Zapnout) { Write-Host "CHYBA: naplanovana uloha '$TaskName' nevznikla - podrobnosti v $App\autostart.log" -ForegroundColor Red }
    elseif (-not $task) { Write-Host "OK: naplanovana uloha '$TaskName' neexistuje." -ForegroundColor Green }
    else { Write-Host "CHYBA: naplanovana uloha '$TaskName' porad existuje - podrobnosti v $App\autostart.log" -ForegroundColor Red }
    Read-Host 'Enter = zavrit'
    exit
}

# zaznam celeho behu s pravy spravce (i chyb) do autostart.log
try { Start-Transcript -Path (Join-Path $App 'autostart.log') -Append | Out-Null } catch {}
Write-Host "Spusteno s pravy spravce: $([Security.Principal.WindowsIdentity]::GetCurrent().Name), autostart pro: $Uzivatel"

function Find-Python {
    $exe = $null
    try { $exe = (& py -3 -c 'import sys; print(sys.executable)') } catch {}
    if (-not $exe) { $exe = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe' }
    $exe = "$exe".Trim()
    if (-not (Test-Path $exe)) { throw "Python nenalezen ($exe)." }
    return $exe
}

function Set-CamAutostart([bool]$enabled) {
    $run = Get-ItemProperty -Path "$UserHive\$RunKey" -Name $CamRunValue -ErrorAction SilentlyContinue
    if (-not $run) {
        Write-Host '  NZXT CAM nema automaticke spusteni - neni co menit.'
        return
    }
    if (-not (Test-Path "$UserHive\$ApprovedKey")) { New-Item -Path "$UserHive\$ApprovedKey" -Force | Out-Null }
    # stejny zapis jako Spravce uloh > Po spusteni: 02 = povoleno, 03 = zakazano
    $first = if ($enabled) { 2 } else { 3 }
    [byte[]]$val = @($first) + (,0 * 11)
    Set-ItemProperty -Path "$UserHive\$ApprovedKey" -Name $CamRunValue -Value $val -Type Binary
    if ($enabled) { Write-Host '  Automaticke spusteni NZXT CAM zapnuto.' }
    else { Write-Host '  Automaticke spusteni NZXT CAM vypnuto (jde zapnout ve Spravci uloh > Po spusteni).' }
}

try {
    # registr prave toho uzivatele, pro ktereho se autostart nastavuje (i kdyz UAC potvrdil jiny ucet)
    $sid = (New-Object Security.Principal.NTAccount($Uzivatel)).Translate([Security.Principal.SecurityIdentifier]).Value
    $UserHive = "Registry::HKEY_USERS\$sid"

    if ($Zapnout) {
        Write-Host "Zapinam automaticke spusteni RGB-LCD pro $Uzivatel ..."
        $python = Find-Python
        $pythonw = Join-Path (Split-Path $python) 'pythonw.exe'
        if (-not (Test-Path $pythonw)) { throw "pythonw.exe nenalezen vedle $python." }
        & $python -c 'import liquidctl, winusbcdc, PIL'
        if ($LASTEXITCODE -ne 0) { throw "V $python chybi liquidctl, winusbcdc nebo Pillow." }
        Write-Host "  Python: $pythonw"

        $action = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$App\rgb_lcd.py`"" -WorkingDirectory $App
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $Uzivatel
        $trigger.Delay = 'PT10S'      # chvili pockat na USB a HWiNFO
        $taskPrincipal = New-ScheduledTaskPrincipal -UserId $Uzivatel -LogonType Interactive -RunLevel Highest
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew `
            -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -Priority 4
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $taskPrincipal `
            -Settings $settings -Force `
            -Description 'LCD displej, pumpa a ventilatory NZXT Kraken (C:\RGB-LCD). Ukonceni: ukoncit.bat' | Out-Null
        Write-Host "  Naplanovana uloha '$TaskName' vytvorena (spusti se 10 s po prihlaseni)."

        Set-CamAutostart $false
        $camApp = Get-Process -Name 'NZXT CAM' -ErrorAction SilentlyContinue
        if ($camApp) {
            Write-Host '  POZOR: NZXT CAM prave bezi - zavri ho (i v oznamovaci oblasti), jinak bude aplikaci prekazet.' -ForegroundColor Yellow
        }

        Write-Host ''
        $answer = Read-Host 'Spustit aplikaci hned na pozadi? Zacne ridit chlazeni podle nastaveni. (A/N)'
        if ($answer -match '^[aAyY]') {
            & $python "$App\ukonceni.py" --ukoncit | Out-Null     # pripadna instance ze spustit.bat
            Start-ScheduledTask -TaskName $TaskName
            Write-Host '  Spusteno. Prubeh je v rgb_lcd.log.'
        } else {
            Write-Host '  Aplikace se spusti pri pristim prihlaseni (nebo spustit_na_pozadi.bat).'
        }
    }

    if ($Vypnout) {
        Write-Host 'Vypinam automaticke spusteni RGB-LCD ...'
        try {
            $python = Find-Python
            & $python "$App\ukonceni.py" --ukoncit
        } catch {
            Write-Host "  Aplikaci se nepodarilo ukoncit: $_" -ForegroundColor Yellow
        }
        if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
            Write-Host "  Naplanovana uloha '$TaskName' smazana."
        } else {
            Write-Host "  Naplanovana uloha '$TaskName' neexistuje."
        }
        Set-CamAutostart $true
    }
    Write-Host ''
    Write-Host 'Hotovo.' -ForegroundColor Green
    $code = 0
} catch {
    Write-Host ''
    Write-Host "CHYBA: $_" -ForegroundColor Red
    Write-Host $_.ScriptStackTrace
    $code = 1
}
try { Stop-Transcript | Out-Null } catch {}
Read-Host 'Enter = zavrit'
exit $code
