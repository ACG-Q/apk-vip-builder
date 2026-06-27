param(
    [switch]$SkipTools
)

$ErrorActionPreference = "Stop"
$BaseDir = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$ToolsDir = Join-Path $BaseDir "tools"
$KeystoreDir = Join-Path $BaseDir "keystore"
$KeystorePath = Join-Path $KeystoreDir "release.keystore"
$PassFile = Join-Path $BaseDir ".keystore_pass"
$ApktoolJar = Join-Path $ToolsDir "apktool_2.11.0.jar"

Write-Host "=== FilterBox VIP Builder Setup ===" -ForegroundColor Cyan

# 1. Create directories
$null = New-Item -ItemType Directory -Path $ToolsDir -Force
$null = New-Item -ItemType Directory -Path $KeystoreDir -Force
$null = New-Item -ItemType Directory -Path (Join-Path $BaseDir "output") -Force

# 2. Generate random keystore
if (-not (Test-Path $KeystorePath)) {
    Write-Host "`nGenerating random release keystore ..." -ForegroundColor Yellow
    $pass = -join ((65..90) + (97..122) + (0..9) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
    $pass | Out-File -FilePath $PassFile -Encoding ascii -NoNewline
    $name = "FilterBox VIP"
    $keytoolPath = if (Test-Path (Join-Path $ToolsDir "jre17\jdk-17.0.19+10-jre\bin\keytool.exe")) {
        Join-Path $ToolsDir "jre17\jdk-17.0.19+10-jre\bin\keytool.exe"
    } else {
        "keytool"
    }
    & $keytoolPath -genkeypair -v `
        -keystore $KeystorePath `
        -alias release `
        -keyalg RSA `
        -keysize 2048 `
        -validity 10000 `
        -storepass $pass `
        -keypass $pass `
        -dname "CN=$name, OU=Development, O=CatchingNow, L=Beijing, S=Beijing, C=CN" 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  OK -> $KeystorePath" -ForegroundColor Green
        Write-Host "  Password saved to $PassFile"
    } else {
        Write-Host "  [ERR] keytool failed. Is JDK installed?" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "`nKeystore already exists: $KeystorePath" -ForegroundColor Green
    if (Test-Path $PassFile) {
        $pass = Get-Content $PassFile -Raw
        Write-Host "  Password: $pass"
    }
}

# 3. Download tools
if (-not $SkipTools) {
    # apktool
    if (-not (Test-Path $ApktoolJar)) {
        Write-Host "`nDownloading apktool ..." -ForegroundColor Yellow
        $url = "https://github.com/iBotPeaches/Apktool/releases/download/v2.11.0/apktool_2.11.0.jar"
        Invoke-WebRequest -Uri $url -OutFile $ApktoolJar -UseBasicParsing
        Write-Host "  OK -> $ApktoolJar" -ForegroundColor Green
    } else {
        Write-Host "`napktool already exists" -ForegroundColor Green
    }

    # JRE 17
    $jreDir = Join-Path $ToolsDir "jre17"
    $jreJava = Join-Path $jreDir "jdk-17.0.19+10-jre" "bin" "java.exe"
    if (-not (Test-Path $jreJava)) {
        Write-Host "`nDownloading JRE 17 ..." -ForegroundColor Yellow
        $url = "https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.19%2B7/OpenJDK17U-jre_x64_windows_hotspot_17.0.19_7.zip"
        $zip = Join-Path $ToolsDir "jre17.zip"
        Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
        Expand-Archive -Path $zip -DestinationPath $jreDir -Force
        Remove-Item $zip -Force
        Write-Host "  OK -> $jreJava" -ForegroundColor Green
    } else {
        Write-Host "`nJRE 17 already exists" -ForegroundColor Green
    }
}

# 4. Git init hint
Write-Host "`n=== Setup complete ===" -ForegroundColor Cyan
Write-Host "`nNext steps:"
Write-Host "  1. git init && git add . && git commit -m 'init'"
Write-Host "  2. Push to GitHub"
Write-Host "  3. Add Secrets to GitHub repo:"
Write-Host "     - RELEASE_KEYSTORE: base64 of $KeystorePath"
Write-Host "     - RELEASE_KEYSTORE_PASS: password from $PassFile"
Write-Host "`n  PowerShell command to get base64:"
Write-Host "    [Convert]::ToBase64String([IO.File]::ReadAllBytes('$KeystorePath'))"
