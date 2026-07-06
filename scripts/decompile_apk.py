"""
decompile_apk.py — 反编译 APK
用法: python scripts/decompile_apk.py --app <app_name>

XAPK 处理: 提取所有 split → apktool 分别反编译 → 目录级全合并 → 清理 manifest。
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

import xapk2apk

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


def run_apktool(java_bin, apk_path, out_dir):
    if out_dir.exists():
        shutil.rmtree(out_dir)
    cmd = [java_bin, "-jar", str(APKTOOL_JAR), "d", "-f", "-o", str(out_dir), str(apk_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"[ERR] apktool failed:\n{proc.stderr.strip()}")
        sys.exit(1)


def _merge_libs(main_dir, src_dir):
    src_lib = src_dir / "lib"
    if not src_lib.exists():
        return
    dst_lib = main_dir / "lib"
    dst_lib.mkdir(exist_ok=True)
    for abi_dir in src_lib.iterdir():
        if not abi_dir.is_dir():
            continue
        dst = dst_lib / abi_dir.name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(abi_dir, dst)


def _merge_res(main_dir, src_dir):
    src_res = src_dir / "res"
    if not src_res.exists():
        return
    for f in src_res.rglob("*"):
        if f.is_dir() or f.name == "public.xml":
            continue
        rel = f.relative_to(src_res)
        dst = main_dir / "res" / rel
        if dst.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)


def _merge_assets(main_dir, src_dir):
    src_pack = src_dir / "assets" / "assetpack"
    if not src_pack.exists():
        return
    dst_pack = main_dir / "assets" / "assetpack"
    dst_pack.mkdir(parents=True, exist_ok=True)
    for f in src_pack.rglob("*"):
        if f.is_dir():
            continue
        rel = f.relative_to(src_pack)
        dst = dst_pack / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)


def _merge_do_not_compress(main_dir, src_dir):
    main_yml = main_dir / "apktool.yml"
    src_yml = src_dir / "apktool.yml"
    if not main_yml.exists() or not src_yml.exists():
        return

    def parse_dnc(path):
        lines = path.read_text(encoding="utf-8").splitlines()
        in_block = False
        items = set()
        for line in lines:
            if re.match(r"^\s*doNotCompress:\s*$", line):
                in_block = True
            elif in_block:
                m = re.match(r"^\s*-\s+(.+)$", line)
                if m:
                    items.add(m.group(1).strip())
                elif line.strip() and not line.startswith((" ", "\t")):
                    break
        return items

    combined = sorted(parse_dnc(main_yml) | parse_dnc(src_yml))
    if not combined:
        return

    lines = main_yml.read_text(encoding="utf-8").splitlines()
    start = end = None
    for i, line in enumerate(lines):
        if re.match(r"^\s*doNotCompress:\s*$", line):
            start = i
        elif start is not None and end is None:
            if re.match(r"^\s*-\s+", line):
                continue
            if line.strip() and not line.startswith((" ", "\t")):
                end = i
                break
    if end is None:
        end = len(lines)

    new_block = [f"  - {item}" for item in combined]
    new_lines = lines[:start + 1] + new_block + lines[end:]
    main_yml.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def extract_xapk(apk_path, java_bin, apktool_out):
    """XAPK — 提取 → 分别 apktool 反编译 → 目录级全合并。"""
    if not xapk2apk.is_xapk(apk_path):
        return False

    print("  XAPK detected, extracting splits ...")

    tmp_dir = apk_path.parent / "_xapk_tmp"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir()

    main_apk = None
    config_apks = []

    with zipfile.ZipFile(apk_path) as z:
        for entry in z.namelist():
            if not entry.endswith(".apk"):
                continue
            if entry.startswith("config."):
                config_apks.append(entry)
            else:
                main_apk = entry
        if not main_apk:
            print("[ERR] No main APK found in XAPK")
            sys.exit(1)

        for apk in [main_apk] + config_apks:
            with z.open(apk) as src, open(tmp_dir / Path(apk).name, "wb") as dst:
                shutil.copyfileobj(src, dst)

    config_paths = [tmp_dir / Path(c).name for c in config_apks]
    main_path = tmp_dir / Path(main_apk).name

    shutil.move(str(main_path), str(apk_path))

    print(f"  Config splits: {[p.name for p in config_paths]}")
    print("\n=== apktool decode (main) ===")
    run_apktool(java_bin, apk_path, apktool_out)

    for cp in config_paths:
        split_out = tmp_dir / cp.stem
        print(f"\n=== apktool decode ({cp.stem}) ===")
        run_apktool(java_bin, cp, split_out)

        _merge_libs(apktool_out, split_out)
        _merge_res(apktool_out, split_out)
        _merge_do_not_compress(apktool_out, split_out)

    shutil.rmtree(tmp_dir)
    return True


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
        print("\n=== apktool decode ===")
        run_apktool(java_bin, apk_path, apktool_out)

    xapk2apk.patch_manifest(apktool_out)
    extract_version(apktool_out, version_out, default_pkg)
    total_files = sum(1 for _ in apktool_out.rglob("*"))
    smali_files = sum(1 for _ in apktool_out.rglob("*.smali"))
    print(f"\n  Total files: {total_files}, smali: {smali_files}")
    print("=== Done ===")


if __name__ == "__main__":
    main()
