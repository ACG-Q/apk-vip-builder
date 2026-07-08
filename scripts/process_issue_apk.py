"""
process_issue_apk.py — 处理 Issue 中上传的 APK

流程:
  1. 从 Issue body 提取附件 URL
  2. 下载 APK
  3. 解析元数据（包名/版本/版本号）
  4. 匹配 app 目录
  5. 更新 app.json（download_url → 附件直链）
  6. 提交 commit

用法:
  python scripts/process_issue_apk.py --issue <number>
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

from parse_apk import parse_apk_metadata, find_app_dir

BASE_DIR = Path(__file__).resolve().parent.parent
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

REPO = os.environ.get("GITHUB_REPOSITORY", "ACG-Q/apk-vip-builder")
TOKEN = os.environ.get("GITHUB_TOKEN", "")


def _req(url, method="GET", data=None):
    """GitHub API 请求。"""
    headers = {
        "User-Agent": UA,
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {TOKEN}",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, headers=headers, method=method, data=data)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def get_issue_body(issue_number):
    """获取 Issue body。"""
    url = f"https://api.github.com/repos/{REPO}/issues/{issue_number}"
    data = _req(url)
    return data.get("body", ""), data.get("number")


def extract_attachment_url(body):
    """从 Issue body 中提取 GitHub Attachment URL。
       新版格式: [filename.apk](https://github.com/user-attachments/...)
       兼容旧版: ### APK 下载链接 ..."""
    # 新版 markdown 链接
    m = re.search(r'\[.*?\]\((https://github\.com/user-attachments/[^\s)]+)\)', body)
    if m:
        return m.group(1)
    # 旧版 ### APK 下载链接
    m = re.search(r'### APK 下载链接\s*\n\s*(https://github\.com/user-attachments/files/\d+/\S+)', body)
    if m:
        return m.group(1)
    # 兜底
    m = re.search(r'https://github\.com/user-attachments/files/\d+/\S+', body)
    if m:
        return m.group(0)
    return None


def extract_attachment_from_comments(issue_number):
    """从 Issue 评论中查找附件 URL（兜底）。"""
    url = f"https://api.github.com/repos/{REPO}/issues/{issue_number}/comments"
    data = _req(url)
    for comment in data:
        body = comment.get("body", "")
        m = re.search(r'https://github\.com/user-attachments/files/\d+/\S+', body)
        if m:
            return m.group(0)
    return None


def download_file(url, dest):
    """下载文件到指定路径。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req) as src, open(dest, "wb") as dst:
        while True:
            chunk = src.read(65536)
            if not chunk:
                break
            dst.write(chunk)
    print(f"  Downloaded: {dest.name} ({dest.stat().st_size / 1024 / 1024:.1f} MB)", flush=True)


def update_app_json(app_name, download_url):
    """更新 app.json 中的 download_url。"""
    app_json = BASE_DIR / "apps" / app_name / "app.json"
    if not app_json.exists():
        print(f"[ERR] app.json not found: {app_json}", flush=True)
        return False

    config = json.loads(app_json.read_text(encoding="utf-8"))
    config["download_url"] = download_url
    app_json.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  Updated apps/{app_name}/app.json", flush=True)
    return True


def git_commit_and_push(app_name, issue_number):
    """提交并推送修改。"""
    cmds = [
        ['git', 'config', 'user.name', 'github-actions[bot]'],
        ['git', 'config', 'user.email', 'github-actions[bot]@users.noreply.github.com'],
        ['git', 'add', f'apps/{app_name}/app.json'],
        ['git', 'commit', '-m', f'auto: update {app_name} download_url from issue #{issue_number}'],
        ['git', 'push'],
    ]
    for cmd in cmds:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0 and 'nothing to commit' not in result.stderr.lower():
            print(f"  git: {result.stderr.strip()}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Process APK from issue")
    parser.add_argument("--issue", required=True, help="Issue number")
    parser.add_argument("--token", default="", help="GitHub token (or GITHUB_TOKEN env)")
    args = parser.parse_args()

    global TOKEN
    if args.token:
        TOKEN = args.token
    if not TOKEN:
        print("[ERR] No GITHUB_TOKEN provided", flush=True)
        sys.exit(1)

    issue_number = args.issue

    # 1. Get issue body
    print(f"Fetching issue #{issue_number} ...", flush=True)
    body, _ = get_issue_body(issue_number)

    # 2. Extract attachment URL (body → comments fallback)
    attachment_url = extract_attachment_url(body)
    if not attachment_url:
        print("  Not found in body, checking comments ...", flush=True)
        attachment_url = extract_attachment_from_comments(issue_number)
    if not attachment_url:
        print("[ERR] No attachment URL found in issue", flush=True)
        sys.exit(1)
    print(f"Attachment URL: {attachment_url[:100]}...", flush=True)

    # 3. Download APK
    apk_path = BASE_DIR / ".tmp" / f"issue_{issue_number}.apk"
    print("Downloading APK ...", flush=True)
    download_file(attachment_url, apk_path)

    # 4. Parse metadata
    print("Parsing APK metadata ...", flush=True)
    info = parse_apk_metadata(str(apk_path))
    print(f"  Package: {info.get('package', '?')}", flush=True)
    print(f"  Version: {info.get('version_name', '?')} (code {info.get('version_code', '?')})", flush=True)

    if not info.get('package'):
        print("[ERR] Could not determine package name", flush=True)
        sys.exit(1)

    # 5. Find matching app
    app_name = find_app_dir(info['package'])
    if not app_name:
        print(f"[ERR] No app found for package: {info['package']}", flush=True)
        sys.exit(1)
    print(f"  Matched app: {app_name}", flush=True)

    # 6. Update app.json
    print("Updating app.json ...", flush=True)
    if not update_app_json(app_name, attachment_url):
        sys.exit(1)

    # 7. Commit
    print("Committing ...", flush=True)
    git_commit_and_push(app_name, issue_number)

    # 8. Set outputs for workflow
    if os.environ.get("GITHUB_OUTPUT"):
        gh_out = os.environ["GITHUB_OUTPUT"]
        with open(gh_out, "a") as f:
            f.write(f"app={app_name}\n")
            f.write(f"url={attachment_url}\n")
            f.write(f"package={info['package']}\n")
            f.write(f"version_name={info.get('version_name', '')}\n")
            f.write(f"version_code={info.get('version_code', 0)}\n")

    # Cleanup
    if apk_path.exists():
        apk_path.unlink()

    print("=== Done ===", flush=True)


if __name__ == "__main__":
    main()
