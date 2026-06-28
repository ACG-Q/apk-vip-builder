"""
create_release.py — 创建 GitHub Release
用法: python scripts/create_release.py --app <app_name>
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description="Create GitHub Release")
    parser.add_argument("--app", required=True)
    args = parser.parse_args()

    info_path = BASE_DIR / "output" / args.app / "release_info.json"
    if not info_path.exists():
        print(f"[ERR] release_info.json not found: {info_path}")
        sys.exit(1)

    info = json.loads(info_path.read_text())

    tag = info["tag"]
    title = info["title"]
    pkg = info["package"]
    ver = info["version"]
    vc = info["version_code"]
    sha = info["sha256"]
    size = info["size"]
    time = info["build_time"]
    apk_name = info["apk_name"]

    body = f"""## {title}

| 项目 | 值 |
|------|-----|
| 包名 | {pkg} |
| 版本 | {ver} ({vc}) |
| SHA256 | `{sha}` |
| 大小 | {size // (1024 * 1024)} MB |
| 构建时间 | {time} |
"""

    apk_path = BASE_DIR / "output" / args.app / apk_name
    if not apk_path.exists():
        print(f"[ERR] APK not found: {apk_path}")
        sys.exit(1)

    cmd = [
        "gh", "release", "create", tag,
        "--title", title,
        "--notes", body,
        f"{apk_path}#{apk_name}",
    ]
    print(f"Creating release: {tag}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[ERR] gh release failed:\n{result.stderr.strip()}")
        sys.exit(1)
    print(f"  OK -> https://github.com/*/releases/tag/{tag}")


if __name__ == "__main__":
    main()
