"""
identify_apk.py — 下载 APK，SHA256 变更检测
用法: python scripts/identify_apk.py --app <app_name>
支持豌豆荚等第三方市场的 URL 自动解析下载
"""

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

from resolve_market import resolve_market_url

BASE_DIR = Path(__file__).resolve().parent.parent
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

REPO = os.environ.get("GITHUB_REPOSITORY", "")
TOKEN = os.environ.get("GITHUB_TOKEN", "")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def resolve_issue_url(url):
    """解析 issue:N 格式为实际的附件下载 URL。"""
    m = re.match(r"^issue:(\d+)$", url)
    if not m:
        return url
    if not TOKEN:
        print("[ERR] GITHUB_TOKEN required for issue:N resolution", flush=True)
        return None

    issue_num = m.group(1)
    api_url = f"https://api.github.com/repos/{REPO}/issues/{issue_num}"
    headers = {
        "User-Agent": UA,
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {TOKEN}",
    }
    req = urllib.request.Request(api_url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())

    body = data.get("body", "")
    m2 = re.search(r"https://github\.com/user-attachments/files/\d+/\S+", body)
    if m2:
        resolved = m2.group(0)
        print(f"  [issue:{issue_num}] Resolved: {resolved[:80]}...", flush=True)
        return resolved

    # Also check comments
    comments_url = f"https://api.github.com/repos/{REPO}/issues/{issue_num}/comments"
    req2 = urllib.request.Request(comments_url, headers=headers)
    with urllib.request.urlopen(req2) as resp:
        comments = json.loads(resp.read().decode())
    for comment in comments:
        body_c = comment.get("body", "")
        m2 = re.search(r"https://github\.com/user-attachments/files/\d+/\S+", body_c)
        if m2:
            resolved = m2.group(0)
            print(f"  [issue:{issue_num}] Resolved from comment: {resolved[:80]}...", flush=True)
            return resolved

    print(f"[ERR] No attachment found in issue #{issue_num}", flush=True)
    return None


def main():
    parser = argparse.ArgumentParser(description="Download APK and detect changes")
    parser.add_argument("--app", required=True)
    parser.add_argument("--url", default="", help="Override download_url from app.json")
    parser.add_argument("--token", default="", help="GitHub token (for issue:N resolution)")
    args = parser.parse_args()

    if args.token:
        global TOKEN
        TOKEN = args.token

    app_dir = BASE_DIR / "apps" / args.app
    app_json = app_dir / "app.json"
    state_file = app_dir / "state.json"
    apk_path = app_dir / "download.apk"

    with open(app_json, encoding="utf-8") as f:
        config = json.load(f)

    state = json.loads(state_file.read_text()) if state_file.exists() else {}

    apk_url = args.url or config.get("download_url", "")
    if apk_url and apk_url.startswith("issue:"):
        apk_url = resolve_issue_url(apk_url)
    elif apk_url:
        apk_url = resolve_market_url(apk_url)
    print(f"App: {config['name']}")
    if apk_url:
        print(f"URL: {apk_url}")

    if not apk_path.exists() and not apk_url:
        print(f"[ERR] APK not found: {apk_path} (no download_url configured)")
        sys.exit(1)

    download = bool(apk_url) and (not apk_path.exists() or sha256(apk_path) != state.get("last_hash", ""))

    if download:
        print("Downloading APK ...")
        req = urllib.request.Request(apk_url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req) as src, open(apk_path, "wb") as dst:
            while True:
                chunk = src.read(65536)
                if not chunk:
                    break
                dst.write(chunk)
        size = apk_path.stat().st_size
        print(f"  OK ({size / 1024 / 1024:.1f} MB)")
        h = sha256(apk_path)
        print(f"SHA256: {h}")
    else:
        if apk_url:
            print("APK unchanged (same hash), skipping download")
        else:
            print("Manual provision APK, checking hash ...")
        h = sha256(apk_path) if apk_path.exists() else state.get("last_hash", "")
        size = apk_path.stat().st_size if apk_path.exists() else 0

    changed = h != state.get("last_hash", "")
    if changed:
        state.update({
            "last_hash": h,
            "last_size": size,
            "last_version": state.get("last_version", ""),
            "last_version_code": state.get("last_version_code", 0),
        })
        app_dir.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(state, indent=2) + "\n")

    result = {"changed": changed, "hash": h, "size": size}
    print(json.dumps(result, indent=2))
    sys.exit(0 if changed else 1)


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
