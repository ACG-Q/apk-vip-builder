"""
markets/wandoujia.py — 豌豆荚 URL 解析器

支持:
  最新版本: wandoujia.com/apps/{id}              → /download/dot 302 Location
  历史版本: wandoujia.com/apps/{id}/history_v{code} → HTML data-href → 302 Location
"""

import html as html_mod
import re
import urllib.request

from resolve_market import register, follow_redirect

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def _fetch_html(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req) as resp:
        return resp.read().decode("utf-8", errors="replace")


@register(r"wandoujia\.com/apps/\d+/history_v", name="wandoujia")
def resolve_wandoujia_history(url):
    """历史版本: HTML 中 data-href → 302 Location。"""
    html = _fetch_html(url)
    m = re.search(r'data-href="([^"]+)"', html)
    if not m:
        print("  [resolve] WARN: no data-href found", flush=True)
        return None
    data_href = html_mod.unescape(m.group(1))
    print(f"  [resolve] data-href: {data_href[:80]}...", flush=True)
    return follow_redirect(data_href) or data_href


@register(r"wandoujia\.com/apps/\d+", name="wandoujia")
def resolve_wandoujia_app(url):
    """最新版本: /download/dot → 302 Location。"""
    m = re.search(r"/apps/(\d+)", url)
    if not m:
        return None
    dot_url = f"https://www.wandoujia.com/apps/{m.group(1)}/download/dot?ch=detail_normal_dl"
    return follow_redirect(dot_url)
