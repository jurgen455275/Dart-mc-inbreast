param(
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$source = Join-Path $root "src\deform_inbreast_h010_threshold_features.cpp"
$output = Join-Path $root "bin\windows"
New-Item -ItemType Directory -Force -Path $output | Out-Null

$gpp = Get-Command g++ -ErrorAction SilentlyContinue
if ($gpp) {
    & $gpp.Source -std=c++17 -O3 -DNDEBUG -shared -static-libgcc -static-libstdc++ $source -o (Join-Path $output "deform_inbreast_h010_threshold_features.dll")
    if ($LASTEXITCODE -ne 0) { throw "Fallo al compilar H010 con g++." }
    $pthread = Join-Path (Split-Path $gpp.Source) "libwinpthread-1.dll"
    if (Test-Path -LiteralPath $pthread) {
        Copy-Item -LiteralPath $pthread -Destination (Join-Path $output "libwinpthread-1.dll") -Force
    }
    Write-Host "H010 compilado con g++."
    exit 0
}

$vsRoots = @(
    "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\Common7\Tools\VsDevCmd.bat",
    "C:\Program Files\Microsoft Visual Studio\18\BuildTools\Common7\Tools\VsDevCmd.bat",
    "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat",
    "C:\Program Files\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat"
)
$vsDevCmd = $vsRoots | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $vsDevCmd) { throw "No se encontro g++ ni Visual Studio Build Tools." }

$dll = Join-Path $output "deform_inbreast_h010_threshold_features.dll"
$lib = Join-Path $output "deform_inbreast_h010_threshold_features.lib"
$compile = "call `"$vsDevCmd`" -arch=x64 -host_arch=x64 >nul && cl /nologo /std:c++17 /O2 /EHsc /MT /DNDEBUG /LD `"$source`" /Fe:`"$dll`" /link /IMPLIB:`"$lib`""
& cmd.exe /d /s /c $compile
if ($LASTEXITCODE -ne 0) { throw "Fallo al compilar H010 con MSVC." }
Write-Host "H010 compilado con MSVC: $dll"
