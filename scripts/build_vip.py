"""
build_vip.py — 编译 + 签名 VIP APK
用法: python scripts/build_vip.py --app <app_name> [--url <repo_url>]
"""

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TOOLS_DIR = BASE_DIR / "tools"
APKTOOL_JAR = TOOLS_DIR / "apktool_2.11.0.jar"
UBER_SIGNER_JAR = TOOLS_DIR / "uber-apk-signer-1.3.0.jar"
KEYSTORE_PATH = BASE_DIR / "keystore" / "release.keystore"
KEYSTORE_PASS_FILE = BASE_DIR / ".keystore_pass"


def find_java():
    for p in (TOOLS_DIR / "jre17").rglob("java*"):
        if p.name in ("java", "java.exe") and os.access(p, os.X_OK):
            return str(p)
    jre_path_file = TOOLS_DIR / "jre17" / ".jre_path"
    if jre_path_file.exists():
        java_path = jre_path_file.read_text().strip()
        if Path(java_path).exists():
            return java_path
    java = shutil.which("java")
    if java:
        return java
    print("[ERR] No Java found. Run: python scripts/download_tools.py")
    sys.exit(1)


def load_patch_module(app_name):
    patch_path = BASE_DIR / "apps" / app_name / "patch.py"
    if not patch_path.exists():
        print(f"[ERR] Patch module not found: {patch_path}")
        sys.exit(1)
    spec = importlib.util.spec_from_file_location(f"{app_name}_patch", patch_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def get_app_config(app_name):
    config_path = BASE_DIR / "apps" / app_name / "app.json"
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def rebuild_apk(java_bin, apktool_dir, unsigned_path):
    print("\n=== apktool build ===")
    cmd = [java_bin, "-jar", str(APKTOOL_JAR), "b", str(apktool_dir), "-o", str(unsigned_path)]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    print(f"  OK -> {unsigned_path}")
    return unsigned_path


def get_keystore():
    keystore_data = os.environ.get("RELEASE_KEYSTORE")
    ks_pass = os.environ.get("RELEASE_KEYSTORE_PASS")

    if KEYSTORE_PATH.exists():
        ks_pass = KEYSTORE_PASS_FILE.read_text().strip() if KEYSTORE_PASS_FILE.exists() else "opencode_vip"
        return str(KEYSTORE_PATH), ks_pass, "release"

    if keystore_data and ks_pass:
        decoded = base64.b64decode(keystore_data)
        KEYSTORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        KEYSTORE_PATH.write_bytes(decoded)
        return str(KEYSTORE_PATH), ks_pass, "release"

    print("[ERR] No keystore found. Run setup.ps1 first.")
    sys.exit(1)


def ensure_uber_signer(java_bin):
    if UBER_SIGNER_JAR.exists():
        return str(UBER_SIGNER_JAR)
    print("Downloading uber-apk-signer ...")
    url = "https://github.com/patrickfav/uber-apk-signer/releases/download/v1.3.0/uber-apk-signer-1.3.0.jar"
    UBER_SIGNER_JAR.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, UBER_SIGNER_JAR)
    return str(UBER_SIGNER_JAR)


def sign_apk(java_bin, unsigned_path, version_info, output_apk_name):
    ks_path, ks_pass, ks_alias = get_keystore()
    signed_dir = unsigned_path.parent / "signed"
    signed_dir.mkdir(parents=True, exist_ok=True)

    uber_jar = ensure_uber_signer(java_bin)
    cmd = [
        java_bin, "-jar", uber_jar,
        "--ks", ks_path,
        "--ksPass", ks_pass,
        "--ksKeyPass", ks_pass,
        "--ksAlias", ks_alias,
        "--apks", str(unsigned_path),
        "--out", str(signed_dir),
    ]
    print(f"\n=== Signing ===")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[ERR] Signer stderr:\n{result.stderr}")
        print(f"[ERR] Signer stdout:\n{result.stdout}")
        sys.exit(1)

    candidates = list(signed_dir.glob("*.apk"))
    raw_path = candidates[0] if candidates else None
    signed_path = signed_dir / output_apk_name
    if raw_path:
        if raw_path != signed_path:
            if signed_path.exists():
                signed_path.unlink()
            raw_path.rename(signed_path)
    print(f"  OK -> {signed_path}")
    return signed_path


def main():
    parser = argparse.ArgumentParser(description="Build VIP APK")
    parser.add_argument("--app", required=True)
    parser.add_argument("--url", default="https://github.com/ACG-Q/apk-vip-builder",
                        help="GitHub repo URL for settings click action")
    args = parser.parse_args()

    app_config = get_app_config(args.app)
    app_name = app_config["name"]
    version_file = BASE_DIR / "output" / args.app / "version.json"
    apktool_dir = BASE_DIR / "output" / args.app / "apktool"
    smali_dir = apktool_dir / "smali"
    output_dir = BASE_DIR / "output" / args.app

    if not smali_dir.exists():
        print(f"[ERR] Smali not found: {smali_dir}. Run decompile_apk.py first.")
        sys.exit(1)

    version_info = json.loads(version_file.read_text()) if version_file.exists() else {"version": "unknown", "version_code": 0, "package": app_config["package"]}

    java_bin = find_java()

    no_res = app_config.get("no_res", False)
    patch_mod = load_patch_module(args.app)
    patch_mod.patch(smali_dir, version_info, args.url, no_res=no_res)

    unsigned_path = output_dir / "unsigned.apk"
    rebuild_apk(java_bin, apktool_dir, unsigned_path)

    pkg = version_info.get("package", app_config["package"])
    ver = version_info.get("version", "unknown")
    vc = str(version_info.get("version_code", "0"))
    now = datetime.now(timezone.utc)
    build_time = now.strftime("%Y%m%d_%H%M%S")
    app_name = app_config["name"]
    output_apk_name = app_config["output_apk"] \
        .replace("{version}", ver) \
        .replace("{package}", pkg) \
        .replace("{version_code}", vc) \
        .replace("{build_time}", build_time) \
        .replace("{app_name}", app_name)
    signed_path = sign_apk(java_bin, unsigned_path, version_info, output_apk_name)

    h = hashlib.sha256()
    with open(signed_path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    sha = h.hexdigest()
    size = signed_path.stat().st_size
    tag = f"{pkg}_{ver}_{build_time}"
    title = f"{pkg} {ver} {now.strftime('%Y-%m-%d %H:%M UTC')} Build"

    release_info = {
        "apk_path": str(signed_path),
        "apk_name": output_apk_name,
        "package": pkg,
        "version": ver,
        "version_code": version_info.get("version_code", 0),
        "sha256": sha,
        "size": size,
        "build_time": now.strftime("%Y-%m-%d %H:%M UTC"),
        "tag": tag,
        "title": title,
    }
    info_path = output_dir / "release_info.json"
    info_path.write_text(json.dumps(release_info, indent=2, ensure_ascii=False) + "\n")
    print(f"\n  Release info -> {info_path}")
    print("=== VIP build complete ===")


if __name__ == "__main__":
    main()
