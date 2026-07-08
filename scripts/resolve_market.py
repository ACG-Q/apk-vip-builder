"""
resolve_market.py — 市场 URL 解析管理器（纯模块，无 CLI）

注册表 + 路由 + 公共工具函数。
各市场解析器在 markets/ 子包中通过 @register 装饰器自动注册。

用法:
  Module: from resolve_market import resolve_market_url
          url = resolve_market_url(url)
  CLI:    python scripts/resolve_market_cli.py <url>

扩展: 新建 markets/<name>.py，用 @register(pattern) 装饰解析函数即可。
"""

import re
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# ── 注册表 ──────────────────────────────────────────────
_RESOLVERS = []  # [(compiled_re, fn, name)]


def register(pattern, name=""):
    """装饰器：注册 URL 匹配规则。"""
    def decorator(fn):
        _RESOLVERS.append((re.compile(pattern), fn, name))
        return fn
    return decorator


# ── 公共工具（供 markets/ 使用）────────────────────────
def follow_redirect(url):
    """请求 URL，仅获取 302 Location，不下载 body。"""
    req = urllib.request.Request(url, headers={"User-Agent": UA})

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(NoRedirect)
    try:
        opener.open(req)
        return None
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308):
            location = e.headers.get("Location", "")
            if location and location.startswith("http"):
                return location
    return None


def fetch_html(url):
    """请求 URL，返回解码后的 HTML 文本。"""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req) as resp:
        return resp.read().decode("utf-8", errors="replace")


# ── 路由 ────────────────────────────────────────────────
def resolve_market_url(url):
    """将市场 URL 解析为直接下载链接。非市场 URL 原样返回。"""
    # 触发 markets/ 子包自动注册（首次调用时加载）
    import markets  # noqa: F401

    for pat, fn, name in _RESOLVERS:
        if pat.search(url):
            print(f"  [resolve] Market: {name}", flush=True)
            try:
                result = fn(url)
            except Exception as e:
                print(f"  [resolve] WARN: resolver {name} failed ({e})", flush=True)
                continue
            if result:
                print(f"  [resolve] Resolved: {result[:100]}...", flush=True)
                return result
            print(f"  [resolve] WARN: resolver {name} returned None", flush=True)
    # 所有解析器均失败，原样返回
    return url
