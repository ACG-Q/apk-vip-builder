"""
decompile_apk.py — 反编译 APK
用法: python scripts/decompile_apk.py --app <app_name>
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TOOLS_DIR = BASE_DIR / "tools"
APKTOOL_JAR = TOOLS_DIR / "apktool_2.11.0.jar"
DLOAD_SCRIPT = BASE_DIR / "scripts" / "download_tools.py"


def ensure_tools():
    if APKTOOL_JAR.exists():
        return
    if DLOAD_SCRIPT.exists():
        subprocess.run([sys.executable, str(DLOAD_SCRIPT)], check=True)
    if not APKTOOL_JAR.exists():
        print(f"[ERR] apktool not found at {APKTOOL_JAR}")
        sys.exit(1)


def extract_xapk(apk_path, java_bin, apktool_out):
    """检测 XAPK 格式，反编译并合并所有 split APKs。

    合并后的目录直接输出到 apktool_out 位置。
    返回 True 表示已完成合并，False 表示普通 APK 需要正常反编译。
    """
    tmp_dir = apk_path.parent / "_xapk_tmp"

    with zipfile.ZipFile(apk_path) as z:
        names = z.namelist()
        if "manifest.json" not in names:
            return False

        print("  XAPK detected, extracting splits ...")
        main_apk = None
        config_apks = []
        for entry in names:
            if not entry.endswith(".apk"):
                continue
            if entry.startswith("config."):
                config_apks.append(entry)
            else:
                main_apk = entry

        if not main_apk:
            print("[ERR] No main APK found in XAPK")
            sys.exit(1)

        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        tmp_dir.mkdir()
        for apk in [main_apk] + config_apks:
            with z.open(apk) as src, open(tmp_dir / Path(apk).name, "wb") as dst:
                shutil.copyfileobj(src, dst)

    main_path = tmp_dir / Path(main_apk).name
    config_paths = [tmp_dir / Path(c).name for c in config_apks]

    # 用主 APK 替换 download.apk
    shutil.move(str(main_path), str(apk_path))

    if not config_paths:
        shutil.rmtree(tmp_dir)
        return False

    print(f"  Config splits: {[p.name for p in config_paths]}")

    # 反编译主 APK → 直接输出到 apktool_out
    print(f"\n=== apktool decode (main) ===")
    cmd = [java_bin, "-jar", str(APKTOOL_JAR), "d", "-f", "-o", str(apktool_out), str(apk_path)]
    print("  Running: java -jar apktool.jar d ...")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"[ERR] apktool failed:\n{proc.stderr.strip()}")
        sys.exit(1)
    print(f"  OK -> main")

    # 反编译每个 config APK 并合并到 apktool_out
    for cp in config_paths:
        split_out = tmp_dir / cp.stem
        print(f"\n=== apktool decode ({cp.stem}) ===")
        cmd = [java_bin, "-jar", str(APKTOOL_JAR), "d", "-f", "-o", str(split_out), str(cp)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            print(f"  [WARN] apktool failed for {cp.stem}, skipping")
            continue
        print(f"  OK -> {cp.stem}")

        # 合并 lib（native libs）— 核心价值
        split_lib = split_out / "lib"
        main_lib = apktool_out / "lib"
        if split_lib.exists():
            if main_lib.exists():
                shutil.rmtree(str(main_lib))
            shutil.copytree(str(split_lib), str(main_lib))
            print(f"  Merged lib/")

        # 合并 assets（如果有）
        split_assets = split_out / "assets"
        main_assets = apktool_out / "assets"
        if split_assets.exists():
            if main_assets.exists():
                for child in split_assets.iterdir():
                    dest = main_assets / child.name
                    if child.is_dir():
                        if dest.exists():
                            shutil.rmtree(str(dest))
                        shutil.copytree(str(child), str(dest))
                    else:
                        shutil.copy2(str(child), str(dest))
            else:
                shutil.copytree(str(split_assets), str(main_assets))
            print(f"  Merged assets/")

    # 清理临时目录
    shutil.rmtree(tmp_dir)
    return True


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


def run_apktool(java_bin, apk_path, out_dir, no_res=False):
    print(f"\n=== apktool decode ===")
    if out_dir.exists():
        shutil.rmtree(out_dir)
    cmd = [java_bin, "-jar", str(APKTOOL_JAR), "d", "-f", "-o", str(out_dir), str(apk_path)]
    if no_res:
        cmd.insert(5, "-r")
        print("  (no-res mode: skipping resource decode)")
    print("  Running: java -jar apktool.jar d ...")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"[ERR] apktool failed:\n{proc.stderr.strip()}")
        sys.exit(1)
    print(f"  OK -> {out_dir}")


def extract_version(out_dir, version_out, default_package="unknown"):
    info = {"version": "", "version_code": 0, "package": ""}

    yml_path = out_dir / "apktool.yml"
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
        xml_path = out_dir / "AndroidManifest.xml"
        if xml_path.exists():
            text = xml_path.read_text(encoding="utf-8", errors="replace")
            m = re.search(r'package="([^"]+)"', text)
            if m:
                info["package"] = m.group(1)

    if not info.get("package"):
        info["package"] = default_package
    version_out.parent.mkdir(parents=True, exist_ok=True)
    version_out.write_text(json.dumps(info, indent=2) + "\n")
    print(f"  Package: {info['package']}")
    return info


def main():
    parser = argparse.ArgumentParser(description="Decompile APK")
    parser.add_argument("--app", required=True)
    args = parser.parse_args()

    apk_path = BASE_DIR / "apps" / args.app / "download.apk"
    if not apk_path.exists():
        print(f"[ERR] APK not found: {apk_path}")
        sys.exit(1)

    app_json = BASE_DIR / "apps" / args.app / "app.json"
    no_res = False
    default_pkg = "unknown"
    if app_json.exists():
        config = json.loads(app_json.read_text(encoding="utf-8"))
        no_res = config.get("no_res", False)
        default_pkg = config.get("package", "unknown")

    apktool_out = BASE_DIR / "output" / args.app / "apktool"
    version_out = BASE_DIR / "output" / args.app / "version.json"

    ensure_tools()
    java_bin = find_java()
    merged = extract_xapk(apk_path, java_bin, apktool_out)
    if not merged:
        run_apktool(java_bin, apk_path, apktool_out, no_res)
    extract_version(apktool_out, version_out, default_pkg)
    total_files = sum(1 for _ in apktool_out.rglob("*"))
    smali_files = sum(1 for _ in apktool_out.rglob("*.smali"))
    print(f"\n  Total files: {total_files}, smali: {smali_files}")
    print("=== Done ===")


if __name__ == "__main__":
    main()
