import hashlib
import json
import sys
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
APK_URL = "https://filterbox.catchingnow.com/latest.apk"
APK_PATH = BASE_DIR / "latest.apk"
CONFIG_PATH = BASE_DIR / "config.json"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def load_config():
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {"last_hash": "", "last_version": "", "last_version_code": 0, "last_size": 0}


def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2) + "\n")


def download_apk():
    print(f"Downloading APK from {APK_URL} ...")
    req = urllib.request.Request(APK_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req) as src, open(APK_PATH, "wb") as dst:
        while True:
            chunk = src.read(65536)
            if not chunk:
                break
            dst.write(chunk)
    size = APK_PATH.stat().st_size
    print(f"  OK ({size / 1024 / 1024:.1f} MB)")
    return size


def main():
    cfg = load_config()
    need_download = True

    if APK_PATH.exists():
        h = sha256(APK_PATH)
        if h == cfg.get("last_hash", ""):
            need_download = False
            print("APK unchanged (same hash), skipping download")

    if need_download:
        size = download_apk()
        h = sha256(APK_PATH)
        print(f"SHA256: {h}")
    else:
        h = cfg["last_hash"]
        size = APK_PATH.stat().st_size

    changed = h != cfg.get("last_hash", "")
    if changed:
        ver_json = BASE_DIR / "output" / "version.json"
        if ver_json.exists():
            v = json.loads(ver_json.read_text())
        else:
            v = {"version": "", "version_code": 0, "package": ""}
        cfg.update({"last_hash": h, "last_size": size, "last_version": v.get("version", ""), "last_version_code": v.get("version_code", 0)})
        save_config(cfg)

    result = {"changed": changed, "hash": h, "size": size}
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    result = main()
    sys.exit(0 if result["changed"] else 1)
