#!/usr/bin/env python3
"""resolve_market CLI 入口。"""
import sys
from resolve_market import resolve_market_url

if len(sys.argv) < 2:
    print("Usage: python resolve_market_cli.py <url>")
    sys.exit(1)

result = resolve_market_url(sys.argv[1])
print(result)
