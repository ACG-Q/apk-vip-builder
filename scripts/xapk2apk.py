#!/usr/bin/env python3
"""
xapk2apk.py — XAPK 合并工具 (库 + CLI)

作为库使用:
    from xapk2apk import is_xapk, merge_xapk_zip, convert_xapk
    if is_xapk(path):
        merge_xapk_zip(path, output)

作为 CLI 使用:
    python scripts/xapk2apk.py app.xapk                      # 转换 + 签名
    python scripts/xapk2apk.py --no-sign app.xapk            # 跳过签名
    python scripts/xapk2apk.py --verify app.xapk             # 签名后验证
    python scripts/xapk2apk.py --output-name clean app.xapk  # 指定输出文件名
    python scripts/xapk2apk.py app1.xapk app2.xapk           # 批量
"""

import argparse
import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
TOOLS_DIR = BASE_DIR / "tools"
APKTOOL_JARS = sorted(TOOLS_DIR.glob("apktool_*.jar"), key=lambda p: p.stat().st_size, reverse=True)
UBER_SIGNER_JAR = TOOLS_DIR / "uber-apk-signer-1.3.0.jar"
KEYSTORE_PATH = BASE_DIR / "keystore" / "release.keystore"
KEYSTORE_PASS_FILE = BASE_DIR / ".keystore_pass"

ARCH_VALUES = {"arm64_v8a", "armeabi_v7a", "armeabi", "x86", "x86_64"}
DPI_ORDER = ["xxxhdpi", "xxhdpi", "xhdpi", "hdpi", "tvdpi", "mdpi", "ldpi", "nodpi"]
SKIP_IN_ZIP_MERGE = {"AndroidManifest.xml", "resources.arsc", "stamp-cert-sha256"}

__all__ = ["is_xapk", "merge_xapk_zip", "convert_xapk", "sign_apk", "patch_manifest"]


# ── Helpers ──────────────────────────────────────────────────────────


def _find_java():
    for p in (TOOLS_DIR / "jre17").rglob("java*"):
        if p.name in ("java", "java.exe"):
            return str(p)
    jre_path_file = TOOLS_DIR / "jre17" / ".jre_path"
    if jre_path_file.exists():
        java_path = jre_path_file.read_text().strip()
        if Path(java_path).exists():
            return java_path
    return shutil.which("java")


def _find_apktool():
    if APKTOOL_JARS:
        java = _find_java()
        if java:
            return ("jar", java, APKTOOL_JARS[0])
    apktool = shutil.which("apktool")
    if apktool:
        return ("cmd", apktool, None)
    return None


def _run_apktool(apktool_info, action, target, output=None):
    kind, exe, jar = apktool_info
    cmd = [exe, "-jar", str(jar)] if kind == "jar" else [exe]
    if action == "d":
        cmd.extend(["d", "-s", "-o", str(output), str(target)])
    elif action == "b":
        cmd.extend(["b", str(target), "-o", str(output)])
    log.debug("  $ %s", " ".join(str(c) for c in cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"apktool {action} 失败: {r.stderr.strip() or r.stdout.strip()}")
    return r


def _classify_apk(apk_name, pkg_name):
    name = apk_name.rsplit(".apk", 1)[0]
    if name in (pkg_name, "base"):
        return "main"
    if name.startswith("config."):
        parts = name.split(".")
        val = parts[1]
        if val.endswith("dpi"):
            return "dpi"
        if val in ARCH_VALUES:
            return "arch"
    return "locale"


def _dpi_priority(name):
    for i, p in enumerate(DPI_ORDER):
        if p in name:
            return i
    return len(DPI_ORDER)


def sign_apk(apk_path):
    """使用项目 keystore 签名 APK。返回 apk_path。"""
    if not KEYSTORE_PATH.exists():
        raise RuntimeError(f"keystore 不存在: {KEYSTORE_PATH}")
    ks_pass = KEYSTORE_PASS_FILE.read_text().strip() if KEYSTORE_PASS_FILE.exists() else "opencode_vip"
    java = _find_java()
    if not java or not UBER_SIGNER_JAR.exists():
        raise RuntimeError("uber-apk-signer 不可用，无法签名")
    signed_dir = apk_path.parent / "_signed"
    signed_dir.mkdir(exist_ok=True)
    cmd = [
        java, "-jar", str(UBER_SIGNER_JAR),
        "--ks", str(KEYSTORE_PATH),
        "--ksPass", ks_pass,
        "--ksKeyPass", ks_pass,
        "--ksAlias", "release",
        "--apks", str(apk_path),
        "--out", str(signed_dir),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"签名失败: {r.stderr.strip()}")
    candidates = list(signed_dir.glob("*.apk"))
    if candidates:
        candidates[0].replace(apk_path)
        shutil.rmtree(signed_dir)
    log.info("  signed")
    return apk_path


def _verify_apk(apk_path):
    java = _find_java()
    if not java:
        log.warning("  无法验证签名: 未找到 Java")
        return False
    apksigner = shutil.which("apksigner")
    if apksigner:
        cmd = [apksigner, "verify", str(apk_path)]
    elif UBER_SIGNER_JAR.exists():
        cmd = [java, "-jar", str(UBER_SIGNER_JAR), "--verify", str(apk_path)]
    else:
        log.warning("  无法验证签名: 未找到签名工具")
        return False
    r = subprocess.run(cmd, capture_output=True, text=True)
    ok = r.returncode == 0
    log.info("  %s", "signature OK" if ok else "签名无效!")
    return ok


# ── 内部合并函数 (用于 convert_xapk 的 apktool 级合并) ────────────────


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


def _clean_signatures(main_dir):
    meta_inf = main_dir / "original" / "META-INF"
    if not meta_inf.exists():
        return
    for name in ["BNDLTOOL.RSA", "BNDLTOOL.SF", "MANIFEST.MF"]:
        (meta_inf / name).unlink(missing_ok=True)


def patch_manifest(main_dir):
    """清理 AndroidManifest.xml 中的 split 相关属性，确保合并后的 APK 可安装。"""
    manifest = main_dir / "AndroidManifest.xml"
    if not manifest.exists():
        return
    text = manifest.read_text(encoding="utf-8")
    original = text

    text = re.sub(r'\s+android:isSplitRequired="[^"]*"', "", text)
    text = re.sub(r'\s+android:requiredSplitTypes="[^"]*"', "", text)
    text = re.sub(r'\s+android:splitTypes="[^"]*"', "", text)
    text = re.sub(r'\s+<meta-data android:name="com\.android\.vending\.splits[^"]*"[^>]*/>', "", text)
    text = re.sub(r'\s+<meta-data android:name="com\.android\.stamp\.[^"]*"[^>]*/>', "", text)
    text = re.sub(r'\s+<meta-data android:name="com\.android\.vending\.derived\.[^"]*"[^>]*/>', "", text)
    text = text.replace(
        'android:value="STAMP_TYPE_DISTRIBUTION_APK"',
        'android:value="STAMP_TYPE_STANDALONE_APK"',
    )

    if text != original:
        manifest.write_text(text, encoding="utf-8")


# ── Public API ────────────────────────────────────────────────────────


def is_xapk(path):
    """快速判断文件是否为 XAPK 格式。"""
    try:
        with ZipFile(path) as z:
            return "manifest.json" in z.namelist()
    except Exception:
        return False


def merge_xapk_zip(xapk_path, output_path):
    """
    ZIP 级别合并 XAPK split APK 为单个 APK。
    速度快，无需 apktool。适用于管道预处理。

    参数:
        xapk_path: XAPK 文件路径
        output_path: 输出 APK 路径

    返回: output_path (Path)
    """
    xapk_path = Path(xapk_path)
    output_path = Path(output_path)

    with ZipFile(xapk_path) as z:
        if "manifest.json" not in z.namelist():
            raise ValueError(f"不是有效的 XAPK 文件: {xapk_path}")

        manifest = json.loads(z.read("manifest.json"))
        pkg_name = manifest.get("package_name", "")

        apk_files = [e for e in z.namelist() if e.endswith(".apk")]
        if not apk_files:
            raise ValueError("XAPK 中未找到 APK 文件")

        main_apk = None
        config_apks = []
        for e in apk_files:
            if _classify_apk(e, pkg_name) == "main":
                main_apk = e
            else:
                config_apks.append(e)

        if not main_apk:
            raise ValueError("XAPK 中未找到主 APK")

        # 读取主 APK 所有条目
        main_entries = {}
        with z.open(main_apk) as f, ZipFile(f) as mz:
            for info in mz.infolist():
                main_entries[info.filename] = mz.read(info.filename)

        # 排序 config: arch → dpi (高→低) → locale
        def config_sort_key(name):
            t = _classify_apk(name, pkg_name)
            if t == "arch":
                return (0, 0)
            if t == "dpi":
                return (1, _dpi_priority(name))
            return (2, 0)

        config_apks.sort(key=config_sort_key)

        existing_dex = sorted(k for k in main_entries if re.match(r"classes\d*\.dex", k))
        dex_counter = len(existing_dex) + 1

        merged_count = {"dex": 0, "lib": 0, "res": 0, "assets": 0}
        for config_name in config_apks:
            with z.open(config_name) as f, ZipFile(f) as cz:
                for info in cz.infolist():
                    name = info.filename
                    if name in main_entries or name in SKIP_IN_ZIP_MERGE:
                        continue
                    if name.endswith(".dex"):
                        new_name = f"classes{dex_counter}.dex"
                        main_entries[new_name] = cz.read(name)
                        merged_count["dex"] += 1
                        dex_counter += 1
                    elif name.startswith("lib/"):
                        main_entries[name] = cz.read(name)
                        merged_count["lib"] += 1
                    elif name.startswith("res/"):
                        main_entries[name] = cz.read(name)
                        merged_count["res"] += 1
                    elif name.startswith("assets/"):
                        main_entries[name] = cz.read(name)
                        merged_count["assets"] += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output_path, "w", ZIP_DEFLATED) as out:
        for name, data in main_entries.items():
            out.writestr(name, data)

    total = sum(merged_count.values())
    log.info("  ZIP merge: main=%d entries, splits=%d, merged=%d entries",
             len(main_entries), len(config_apks), total)

    return output_path


def convert_xapk(xapk_path, output_dir=None, do_sign=True, apktool_info=None, output_name=None):
    """
    apktool 级完整转换 XAPK 为单个 APK。
    流程: 提取 → apktool 反编译每个 split → 目录级合并 → 清理 → 重编 → 签名

    参数:
        xapk_path: XAPK 文件路径
        output_dir: 输出目录 (默认: xapk 所在目录)
        do_sign: 是否签名 (默认 True)
        apktool_info: apktool 信息，None 时自动查找
        output_name: 输出文件名 (不含扩展名)，默认使用 xapk 文件原名

    返回: 输出 APK 路径 (Path)
    """
    xapk_path = Path(xapk_path)
    output_dir = Path(output_dir) if output_dir else xapk_path.parent

    if apktool_info is None:
        apktool_info = _find_apktool()
        if not apktool_info:
            raise RuntimeError("未找到 apktool")

    stem = output_name or xapk_path.stem
    output_apk = output_dir / f"{stem}.apk"

    with tempfile.TemporaryDirectory(prefix="xapk2apk_") as tmp_str:
        tmp = Path(tmp_str)

        with ZipFile(xapk_path, "r") as zf:
            zf.extractall(tmp)

        manifest_path = tmp / "manifest.json"
        if not manifest_path.exists():
            raise RuntimeError("xapk 内缺少 manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        pkg_name = manifest.get("package_name", "")

        apk_groups = {}
        for f in tmp.iterdir():
            if f.suffix == ".apk" and f.is_file():
                apk_type = _classify_apk(f.name, pkg_name)
                apk_groups.setdefault(apk_type, []).append({
                    "file": f,
                    "dir": tmp / f.stem,
                    "name": f.name,
                })

        if "main" not in apk_groups:
            raise RuntimeError("未找到主 APK")

        main = apk_groups["main"][0]
        total = sum(len(v) for v in apk_groups.values())

        for i, (apk_type, entries) in enumerate(apk_groups.items()):
            for entry in entries:
                log.info("  [%d/%d] 反编译 %s (%s)", i + 1, total, entry["name"], apk_type)
                _run_apktool(apktool_info, "d", entry["file"], entry["dir"])

        log.info("  合并 split apk...")
        for entry in apk_groups.get("arch", []):
            _merge_libs(main["dir"], entry["dir"])
            _merge_do_not_compress(main["dir"], entry["dir"])

        for entry in sorted(apk_groups.get("dpi", []), key=lambda e: _dpi_priority(e["name"])):
            _merge_res(main["dir"], entry["dir"])

        for entry in apk_groups.get("locale", []):
            _merge_res(main["dir"], entry["dir"])
            _merge_assets(main["dir"], entry["dir"])
            _merge_do_not_compress(main["dir"], entry["dir"])

        log.info("  清理签名 & 修补 Manifest...")
        _clean_signatures(main["dir"])
        patch_manifest(main["dir"])

        log.info("  重新打包 APK...")
        rebuilt = tmp / "built.apk"
        _run_apktool(apktool_info, "b", main["dir"], rebuilt)

        output_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(rebuilt, output_apk)

    if do_sign:
        sign_apk(output_apk)

    size = output_apk.stat().st_size
    log.info("  OK -> %s (%d MB)", output_apk, size // 1024 // 1024)
    return output_apk


# ── CLI ───────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="xapk → apk 合并工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  %(prog)s app.xapk                          # 转换 + 签名 (默认)\n"
            "  %(prog)s --no-sign app.xapk                # 跳过签名\n"
            "  %(prog)s --verify app.xapk                 # 签名后验证\n"
            "  %(prog)s --output-name myapp app.xapk      # 指定输出文件名\n"
            "  %(prog)s app1.xapk app2.xapk               # 批量\n"
        ),
    )
    parser.add_argument("files", nargs="+", metavar="FILE.xapk", help="要转换的 xapk 文件")
    parser.add_argument("--no-sign", action="store_true", help="跳过签名")
    parser.add_argument("--verify", action="store_true", help="签名后验证 APK")
    parser.add_argument("--output-name", default=None, help="输出文件名 (不含 .apk)，默认使用 xapk 原名")
    parser.add_argument("-o", "--output", default=None, help="输出目录 (默认: 与输入相同)")
    parser.add_argument("-q", "--quiet", action="store_true", help="安静模式")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO, format="%(message)s")

    apktool_info = _find_apktool()
    if not apktool_info:
        log.error("未找到 apktool。请安装 apktool 或放入 tools/apktool_*.jar。")
        sys.exit(2)

    for xapk_path_str in args.files:
        xapk_path = Path(xapk_path_str)
        if not xapk_path.exists():
            log.error("文件不存在: %s", xapk_path)
            continue
        if xapk_path.suffix.lower() not in (".xapk", ".zip"):
            log.warning("跳过非 xapk 文件: %s", xapk_path)
            continue
        output_dir = Path(args.output) if args.output else xapk_path.parent
        try:
            result = convert_xapk(xapk_path, output_dir, do_sign=not args.no_sign,
                                  apktool_info=apktool_info, output_name=args.output_name)
            if args.verify:
                _verify_apk(result)
        except Exception as e:
            log.error("转换失败: %s", e)


if __name__ == "__main__":
    main()
