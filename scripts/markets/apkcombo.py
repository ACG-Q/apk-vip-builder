"""
markets/apkcombo.py — APKCombo URL 解析器

支持:
   下载页面: apkcombo.com/.../{pkg}/download/apk  → HTML 解析 → 重定向链 → 直链
"""

import re
import html as html_mod
import urllib.request
import urllib.error

from resolve_market import register

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
MAX_REDIRECTS = 10


def _fetch_html(url):
    """请求 URL，返回解码后的 HTML 文本。"""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _follow_redirect_chain(url):
    """跟随重定向链直至最终 URL。"""
    for _ in range(MAX_REDIRECTS):
        req = urllib.request.Request(url, headers={"User-Agent": UA})

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        opener = urllib.request.build_opener(NoRedirect)
        try:
            opener.open(req, timeout=30)
            return url
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308):
                location = e.headers.get("Location", "")
                if location:
                    url = location
                else:
                    return None
            else:
                return None
    return url


@register(r"apkcombo\.com/.+/download/apk$", name="apkcombo")
def resolve_apkcombo_download(url):
    """APKCombo 下载页面 → 解析文件列表 → 跟随重定向 → 返回直链"""

    # 1. 获取下载页面 HTML
    html = _fetch_html(url)

    # 2. 从文件列表中提取下载链接
    m = re.search(r'<a\s+href="([^"]+)"\s+class="variant\s+octs"', html)
    if not m:
        print("  [resolve] WARN: no download link found in file-list", flush=True)
        return None

    redirect_url = html_mod.unescape(m.group(1))
    print(f"  [resolve] Redirect URL: {redirect_url[:100]}...", flush=True)

    # 3. 跟随重定向链（可能多次 302）获取最终直链
    final_url = _follow_redirect_chain(redirect_url)
    if final_url:
        print(f"  [resolve] Final URL: {final_url[:100]}...", flush=True)

    return final_url
