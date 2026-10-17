# Builds dist\zhime-<ver>-win64.zip: bundled Python + numpy/wordfreq + engine + models.
#   pwsh -File install\build_release.ps1
# Needs data\lexicon.pkl and data\bigram.pkl (see README) and the dev .venv (for uv's target python).
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$ver = '0.1.0'
$py = '3.12.10'  # last 3.12 with an embeddable zip on python.org
$out = "$root\dist\zhime-$ver-win64"
$zhime = "$out\zhime"

if (Test-Path $out) { Remove-Item $out -Recurse -Force }
New-Item -ItemType Directory $zhime | Out-Null

$embed = "$root\downloads\python-$py-embed-amd64.zip"
if (-not (Test-Path $embed)) {
    New-Item -ItemType Directory -Force "$root\downloads" | Out-Null
    Invoke-WebRequest "https://www.python.org/ftp/python/$py/python-$py-embed-amd64.zip" -OutFile $embed
}
Expand-Archive $embed "$zhime\python"
# Embedded Python only searches what ._pth lists.
Set-Content "$zhime\python\python312._pth" "python312.zip`n.`n..\src`nLib\site-packages" -Encoding ascii
uv pip install --python "$root\.venv\Scripts\python.exe" --target "$zhime\python\Lib\site-packages" numpy wordfreq
if ($LASTEXITCODE) { throw 'uv pip install failed' }

robocopy "$root\pime_backend" $zhime /E /XD __pycache__ /NFL /NDL /NJH /NJS | Out-Null
robocopy "$root\src\zhime" "$zhime\src\zhime" /E /XD __pycache__ /NFL /NDL /NJH /NJS | Out-Null
New-Item -ItemType Directory "$zhime\data" | Out-Null
Copy-Item "$root\data\lexicon.pkl", "$root\data\bigram.pkl" "$zhime\data"

# Windows PowerShell 5.1 reads BOM-less .ps1 as ANSI, which garbles the Chinese messages.
$ps1 = Get-Content -Raw "$PSScriptRoot\install.ps1" -Encoding utf8
[IO.File]::WriteAllText("$out\install.ps1", $ps1, (New-Object Text.UTF8Encoding $true))
Copy-Item "$PSScriptRoot\安裝.bat", "$PSScriptRoot\解除安裝.bat", "$PSScriptRoot\README.txt" $out
Copy-Item "$root\NOTICE.txt", "$root\LICENSE" $out

Compress-Archive $out "$out.zip" -Force
Get-Item "$out.zip" | Select-Object Name, @{ n = 'MB'; e = { [math]::Round($_.Length / 1MB) } }
