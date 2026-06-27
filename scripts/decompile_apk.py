import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TOOLS_DIR = BASE_DIR / "tools"
APK_PATH = BASE_DIR / "latest.apk"
APKTOOL_OUT = BASE_DIR / "output" / "apktool"
JADX_JAVA = TOOLS_DIR / "jre17" / "jdk-17.0.19+10-jre" / "bin" / "java.exe"
APKTOOL_JAR = TOOLS_DIR / "apktool_2.11.0.jar"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def download(url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req) as src, open(dest, "wb") as dst:
        while True:
            chunk = src.read(65536)
            if not chunk:
                break
            dst.write(chunk)


def ensure_tools():
    if not APKTOOL_JAR.exists():
        print("Downloading apktool ...")
        download("https://github.com/iBotPeaches/Apktool/releases/download/v2.11.0/apktool_2.11.0.jar", APKTOOL_JAR)
        print(f"  OK -> {APKTOOL_JAR}")

    java = JADX_JAVA
    if not java.exists():
        jre17_dir = TOOLS_DIR / "jre17"
        print("Downloading JRE 17 ...")
        zip_path = TOOLS_DIR / "jre17.zip"
        download(
            "https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.19%2B7/OpenJDK17U-jre_x64_windows_hotspot_17.0.19_7.zip",
            zip_path,
        )
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(jre17_dir)
        zip_path.unlink()
        print(f"  OK -> {java}")


def find_java():
    if JADX_JAVA.exists():
        return str(JADX_JAVA)
    java = shutil.which("java")
    if java:
        return java
    print("[ERR] No Java found")
    sys.exit(1)


def run_apktool(java_bin):
    print("\n=== apktool decode ===")
    if APKTOOL_OUT.exists():
        shutil.rmtree(APKTOOL_OUT)
    cmd = [java_bin, "-jar", str(APKTOOL_JAR), "d", "-f", "-o", str(APKTOOL_OUT), str(APK_PATH)]
    print("  Running: java -jar apktool.jar d ...")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"[ERR] apktool failed:\n{proc.stderr.strip()}")
        sys.exit(1)
    print(f"  OK -> {APKTOOL_OUT}")


def extract_version():
    import re
    info = {"version": "", "version_code": 0, "package": ""}

    yml_path = APKTOOL_OUT / "apktool.yml"
    if yml_path.exists():
        text = yml_path.read_text(encoding="utf-8")
        m = re.search(r'versionCode:\s*(\d+)', text)
        if m:
            info["version_code"] = int(m.group(1))
        m = re.search(r'versionName:\s*(\S+)', text)
        if m:
            info["version"] = m.group(1).strip("'\"")
        m = re.search(r'renameManifestPackage:\s*(\S+)', text)
        if m:
            pkg = m.group(1).strip("'\"")
            if pkg.lower() != 'null':
                info["package"] = pkg
        print(f"  Version: {info['version']} (code {info['version_code']})")

    if not info.get("package"):
        xml_path = APKTOOL_OUT / "AndroidManifest.xml"
        if xml_path.exists():
            text = xml_path.read_text(encoding="utf-8", errors="replace")
            m = re.search(r'package="([^"]+)"', text)
            if m:
                info["package"] = m.group(1)
        if not info.get("package"):
            info["package"] = "com.catchingnow.np"

    ver_path = BASE_DIR / "output" / "version.json"
    ver_path.parent.mkdir(parents=True, exist_ok=True)
    ver_path.write_text(json.dumps(info, indent=2) + "\n")
    print(f"  Package: {info['package']}")
    return info


def main():
    if not APK_PATH.exists():
        print(f"[ERR] APK not found: {APK_PATH}")
        sys.exit(1)
    ensure_tools()
    java_bin = find_java()
    run_apktool(java_bin)
    extract_version()
    total_files = sum(1 for _ in APKTOOL_OUT.rglob("*"))
    smali_files = sum(1 for _ in APKTOOL_OUT.rglob("*.smali"))
    print(f"\n  Total files: {total_files}, smali: {smali_files}")
    print("=== Done ===")


if __name__ == "__main__":
    main()
