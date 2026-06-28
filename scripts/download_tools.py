"""
download_tools.py — 下载 apktool + JRE 17（跨平台，幂等）
用法: python scripts/download_tools.py
"""

import json
import os
import platform
import shutil
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TOOLS_DIR = BASE_DIR / "tools"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

APKTOOL_VERSION = "2.11.0"
APKTOOL_URL = f"https://github.com/iBotPeaches/Apktool/releases/download/v{APKTOOL_VERSION}/apktool_{APKTOOL_VERSION}.jar"
APKTOOL_JAR = TOOLS_DIR / f"apktool_{APKTOOL_VERSION}.jar"

JRE_DIR = TOOLS_DIR / "jre17"
JRE_PATH_FILE = JRE_DIR / ".jre_path"


def download(url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req) as src, open(dest, "wb") as dst:
        while True:
            chunk = src.read(65536)
            if not chunk:
                break
            dst.write(chunk)


def download_apktool():
    if APKTOOL_JAR.exists():
        print(f"  [SKIP] apktool already exists: {APKTOOL_JAR}")
        return
    print("  Downloading apktool ...")
    download(APKTOOL_URL, APKTOOL_JAR)
    print(f"  OK -> {APKTOOL_JAR}")


def _os_arch():
    system = platform.system().lower()
    arch = platform.machine().lower()
    if arch in ("amd64", "x86_64"):
        arch = "x64"
    elif arch in ("aarch64", "arm64"):
        arch = "aarch64"
    else:
        arch = "x64"
    os_map = {"windows": "windows", "linux": "linux", "darwin": "mac"}
    return os_map.get(system, "linux"), arch


def _find_java_in_dir(directory):
    for root, _dirs, files in os.walk(directory):
        for f in files:
            if f in ("java", "java.exe"):
                return Path(root) / f
    return None


def download_jre():
    if JRE_PATH_FILE.exists():
        actual = JRE_PATH_FILE.read_text().strip()
        if Path(actual).exists():
            print(f"  [SKIP] JRE already set up: {actual}")
            return
        print("  [INFO] .jre_path points to missing file, re-downloading")

    os_name, arch = _os_arch()
    ext = "zip" if os_name == "windows" else "tar.gz"
    archive_path = TOOLS_DIR / f"jre17.{ext}"

    # Strategy 1: Adoptium API (most reliable)
    api_url = f"https://api.adoptium.net/v3/assets/latest/17/hotspot?image_type=jre&os={os_name}&arch={arch}"
    print(f"  Querying Adoptium API: {api_url}")
    try:
        req = urllib.request.Request(api_url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        if isinstance(data, list) and len(data) > 0:
            binary = data[0].get("binaries", [{}])[0]
            pkg = binary.get("package", {})
            link = pkg.get("link")
            if link:
                print(f"  Downloading JRE 17 ({os_name}/{arch}) ...")
                download(link, archive_path)
                _extract_jre(archive_path, JRE_DIR, ext)
                print(f"  OK -> {JRE_DIR}")
                return
            else:
                print("  API response missing download link")
        else:
            print(f"  API returned empty list")
    except Exception as e:
        print(f"  API query failed: {e}")

    # Strategy 2: Adoptium well-known release
    # Use latest known working version as fallback
    print("  Falling back to well-known JRE 17 release ...")
    version = "jdk-17.0.19%2B7"
    if os_name == "windows":
        filename = f"OpenJDK17U-jre_{arch}_windows_hotspot_17.0.19_7.zip"
    elif os_name == "mac":
        filename = f"OpenJDK17U-jre_{arch}_mac_hotspot_17.0.19_7.tar.gz"
    else:
        filename = f"OpenJDK17U-jre_{arch}_linux_hotspot_17.0.19_7.tar.gz"
    url = f"https://github.com/adoptium/temurin17-binaries/releases/download/{version}/{filename}"
    print(f"  Downloading JRE 17 ({os_name}/{arch}) ...")
    download(url, archive_path)
    _extract_jre(archive_path, JRE_DIR, ext)
    print(f"  OK -> {JRE_DIR}")


def _extract_jre(archive_path, dest_dir, ext):
    dest_dir.mkdir(parents=True, exist_ok=True)
    if ext == "zip":
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(dest_dir)
    else:
        with tarfile.open(archive_path, "r:gz") as tf:
            tf.extractall(dest_dir)
    archive_path.unlink()

    java_bin = _find_java_in_dir(dest_dir)
    if java_bin:
        JRE_PATH_FILE.write_text(str(java_bin.resolve()))
        print(f"  JRE java: {java_bin.resolve()}")
    else:
        print("  [WARN] java not found in extracted JRE")


def main():
    print("=== Download tools ===")
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)

    download_apktool()

    sys_java = shutil.which("java")
    if sys_java:
        print(f"  [SKIP] JRE download (system java: {sys_java})")
    else:
        download_jre()

    print("=== Done ===")


if __name__ == "__main__":
    main()
