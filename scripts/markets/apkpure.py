"""
markets/apkpure.py — APKPure URL 解析器

支持:
  直链: d.apkpure.com/b/XAPK/{pkg}?version=latest  → 302 Location
  页面: apkpure.com/.../{pkg}                       → 构造直链 → 302 Location
"""

import re
import urllib.request

from resolve_market import register, follow_redirect

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


@register(r"d\.apkpure\.com/b/", name="apkpure")
def resolve_apkpure_direct(url):
    """d.apkpure.com 直链 → 302 Location。"""
    return follow_redirect(url)


@register(r"apkpure\.com/.+/([a-zA-Z0-9_.]+)$", name="apkpure")
def resolve_apkpure_page(url):
    """apkpure.com 页面 → 提取包名 → 构造直链 → 302 Location。"""
    m = re.search(r"apkpure\.com/.+/([a-zA-Z0-9_.]+)$", url)
    if not m:
        return None
    pkg = m.group(1)
    direct = f"https://d.apkpure.com/b/XAPK/{pkg}?version=latest"
    print(f"  [resolve] Package: {pkg}", flush=True)
    return follow_redirect(direct)
