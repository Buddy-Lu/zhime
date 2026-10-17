# zhime 安裝／解除安裝。由 安裝.bat / 解除安裝.bat 呼叫，以一般使用者身分執行；
# 需要管理員的部分會用 -Admin 自己再開一次（只跳一次 UAC）。
param([switch]$Uninstall, [switch]$Admin)
$ErrorActionPreference = 'Stop'

$pime = (Get-ItemProperty 'HKLM:\Software\PIME' -ErrorAction SilentlyContinue).'(default)'
if (-not $pime) { $pime = 'C:\Program Files (x86)\PIME' }
# PIME text service CLSID + zhime profile GUID (pime_backend\input_methods\zhime\ime.json)
$tip = '0404:{35F67E9D-A54D-4177-9697-8B0AB71A9E04}{91C07699-318C-401B-B934-56EF6706DA0B}'

function Register-Pime {
    foreach ($arch in 'x86', 'x64') {
        $dll = "$pime\$arch\PIMETextService.dll"
        if (Test-Path $dll) {
            # /u first so profiles of removed backends disappear too
            Start-Process "$env:SystemRoot\System32\regsvr32.exe" -ArgumentList '/u', '/s', "`"$dll`"" -Wait
            Start-Process "$env:SystemRoot\System32\regsvr32.exe" -ArgumentList '/s', "`"$dll`"" -Wait
        }
    }
}

function Set-Backends($keepZhime) {
    $file = "$pime\backends.json"
    if (-not (Test-Path "$file.orig")) { Copy-Item $file "$file.orig" }
    $list = Get-Content -Raw $file | ConvertFrom-Json
    $list = @($list | Where-Object { $_.name -ne 'zhime' })
    if ($keepZhime) {
        $list += [pscustomobject]@{ name = 'zhime'; command = 'zhime\python\python.exe'
                                    workingDir = 'zhime'; params = 'server.py' }
    }
    $json = ConvertTo-Json -InputObject $list -Depth 3
    [IO.File]::WriteAllText($file, $json, (New-Object Text.UTF8Encoding $false))
}

if ($Admin) {
    try {
        Start-Process "$pime\PIMELauncher.exe" -ArgumentList '/quit' -Wait
        if ($Uninstall) {
            Set-Backends $false
            if (Test-Path "$pime\zhime") { Remove-Item "$pime\zhime" -Recurse -Force }
        } else {
            robocopy "$PSScriptRoot\zhime" "$pime\zhime" /MIR /NFL /NDL /NJH /NJS | Out-Null
            if ($LASTEXITCODE -ge 8) { throw "複製檔案失敗 (robocopy $LASTEXITCODE)" }
            Set-Backends $true
        }
        Register-Pime
        exit 0
    } catch {
        Write-Host $_ -ForegroundColor Red
        Read-Host '按 Enter 關閉'
        exit 1
    }
}

if (-not (Test-Path "$pime\PIMELauncher.exe")) {
    Write-Host '找不到 PIME。請先安裝 PIME，再執行一次：' -ForegroundColor Red
    Write-Host '  https://github.com/EasyIME/PIME/releases'
    exit 1
}
if (-not $Uninstall -and -not (Test-Path "$PSScriptRoot\zhime\python\python.exe")) {
    Write-Host '找不到 zhime 資料夾。請先把整個 zip 解壓縮，再從解壓縮後的資料夾執行。' -ForegroundColor Red
    exit 1
}

Write-Host '需要管理員權限，請在 UAC 視窗按「是」…'
$elevated = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"", '-Admin')
if ($Uninstall) { $elevated += '-Uninstall' }
$p = Start-Process powershell.exe -Verb RunAs -Wait -PassThru -ArgumentList $elevated
if ($p.ExitCode -ne 0) { Write-Host '失敗，沒有完成。' -ForegroundColor Red; exit 1 }

# Per-user part, as the normal user: keyboard list + launcher.
$langs = Get-WinUserLanguageList
$zh = $langs | Where-Object LanguageTag -eq 'zh-Hant-TW'
if ($Uninstall) {
    if ($zh -and $zh.InputMethodTips.Contains($tip)) {
        [void]$zh.InputMethodTips.Remove($tip)
        Set-WinUserLanguageList $langs -Force
    }
} else {
    if (-not $zh) {
        $langs.Add('zh-Hant-TW')
        $zh = $langs | Where-Object LanguageTag -eq 'zh-Hant-TW'
    }
    if (-not $zh.InputMethodTips.Contains($tip)) { $zh.InputMethodTips.Add($tip) }
    Set-WinUserLanguageList $langs -Force
}
Start-Process "$pime\PIMELauncher.exe"

if ($Uninstall) {
    Write-Host '已移除 zhime。' -ForegroundColor Green
    if (-not (Get-Content -Raw "$pime\backends.json" | ConvertFrom-Json)) {
        Write-Host 'PIME 裡已經沒有其他輸入法，可以到「設定 > 應用程式」移除 PIME。'
    }
} else {
    Write-Host '安裝完成！按 Win+Space 切換到「智慧注音 (zhime)」。第一次打字要等幾秒載入模型。' -ForegroundColor Green
}
