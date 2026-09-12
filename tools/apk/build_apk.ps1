<#
Build a one-button "pet chat page" APK from a URL.

  .\build_apk.ps1                                  # URL comes from the clipboard
  .\build_apk.ps1 -Url "http://192.168.1.5:8848/?k=abcd1234"
  .\build_apk.ps1 -Label "Address 1" -OutFile .\pet-chat.apk

Right-click the desktop pet -> "Copy chat page address" puts the URL (with its
token) on the clipboard, so running this script with no arguments is enough.

Requirements (see README.md in this folder):
  * JDK 17 on PATH
  * Gradle 8.x        -> set GRADLE_HOME or pass -GradleHome
  * Android SDK       -> set ANDROID_SDK_ROOT or pass -AndroidSdk
#>
param(
    [string]$Url,
    [string]$Label = "Open chat",
    [string]$OutFile = "",
    [string]$GradleHome = $env:GRADLE_HOME,
    [string]$AndroidSdk = $env:ANDROID_SDK_ROOT
)

$ErrorActionPreference = "Stop"
$utf8 = New-Object System.Text.UTF8Encoding($false)
$root = $PSScriptRoot
$work = Join-Path $env:TEMP "pet-apk-build"

function Fail($msg) { Write-Host "ERROR: $msg" -ForegroundColor Red; exit 1 }

function Get-GradleBin {
    if ($GradleHome) {
        $bat = Join-Path $GradleHome "bin\gradle.bat"
        if (Test-Path $bat) { return $bat }
        Fail "no gradle.bat under GRADLE_HOME=$GradleHome"
    }
    $cmd = Get-Command gradle -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($guess in (Get-ChildItem "D:\gradle-*" -Directory -ErrorAction SilentlyContinue |
                        Sort-Object Name -Descending)) {
        $bat = Join-Path $guess.FullName "bin\gradle.bat"
        if (Test-Path $bat) { return $bat }
    }
    Fail "Gradle not found. Set GRADLE_HOME (e.g. D:\gradle-8.7) or pass -GradleHome."
}

function Get-AndroidSdk {
    if ($AndroidSdk) { return $AndroidSdk }
    if ($env:ANDROID_HOME) { return $env:ANDROID_HOME }
    if (Test-Path "D:\android-sdk") { return "D:\android-sdk" }
    Fail "Android SDK not found. Set ANDROID_SDK_ROOT or pass -AndroidSdk."
}

if (-not (Get-Command java -ErrorAction SilentlyContinue)) {
    Fail "java not found on PATH (JDK 17 required)."
}

# ---- 1. get the URL (clipboard first: right-click the pet -> Copy chat page address)
if (-not $Url) {
    try { $clip = (Get-Clipboard -Raw) } catch { $clip = "" }
    if ($clip) { $clip = $clip.Trim() }
    if ($clip -and $clip -match '^https?://') { $Url = $clip }
}
if (-not $Url) { $Url = (Read-Host "Paste the chat page URL").Trim() }
if ($Url -notmatch '^https?://') { Fail "that does not look like a URL: $Url" }
if ($Url -notmatch '\?k=') { Write-Host "WARN: no ?k= token in the URL; the page may refuse it." }

# ---- 2. copy the template into a scratch folder and fill in the URL
if (Test-Path $work) { Remove-Item -Recurse -Force $work }
New-Item -ItemType Directory -Path $work | Out-Null
Copy-Item -Recurse -Force (Join-Path $root "template\*") $work

$javaPath = Join-Path $work "app\src\main\java\com\toki\petchat\MainActivity.java"
if (-not (Test-Path $javaPath)) { Fail "template is incomplete: $javaPath missing" }
$escUrl = $Url.Replace('\', '\\').Replace('"', '\"')
$escLabel = $Label.Replace('\', '\\').Replace('"', '\"')
$java = [IO.File]::ReadAllText($javaPath)
$java = $java.Replace('__URL__', $escUrl).Replace('__LABEL__', $escLabel)
[IO.File]::WriteAllText($javaPath, $java, $utf8)

$sdk = (Get-AndroidSdk)
$props = "sdk.dir=" + $sdk.Replace('\', '\\') + "`n"
[IO.File]::WriteAllText((Join-Path $work "local.properties"), $props, $utf8)

Write-Host "URL   : $Url"
Write-Host "Label : $Label"
Write-Host "Build : $work"

# ---- 3. build
$gradle = Get-GradleBin
if (-not $env:GRADLE_USER_HOME) {
    $env:GRADLE_USER_HOME = Join-Path $env:USERPROFILE ".gradle"
}
Push-Location $work
try {
    & $gradle assembleDebug --no-daemon
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}
if ($code -ne 0) { Fail "gradle failed (exit $code)" }

$built = Join-Path $work "app\build\outputs\apk\debug\app-debug.apk"
if (-not (Test-Path $built)) { Fail "gradle finished but no APK at $built" }

# ---- 4. hand the APK over
if (-not $OutFile) { $OutFile = Join-Path (Get-Location).Path "desktop-pet-chat.apk" }
Copy-Item -Force $built $OutFile
$size = [math]::Round((Get-Item $OutFile).Length / 1KB, 1)
Write-Host ""
Write-Host "APK ready: $OutFile ($size KB)" -ForegroundColor Green
Write-Host "Install  : adb install -r `"$OutFile`"   (or copy the file to the phone and tap it)"
