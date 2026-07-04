"""
markets/ — 应用市场解析器包
自动发现并 import 同目录下所有 *.py，触发 @register 注册。
"""

import importlib
import pkgutil
from pathlib import Path

# 自动 import 同目录下所有模块（触发 @register 装饰器）
_package_dir = Path(__file__).parent
_package_name = __name__  # "markets"
for _finder, _name, _ispkg in pkgutil.iter_modules([str(_package_dir)]):
    if _name.startswith("_"):
        continue
    importlib.import_module(f"{_package_name}.{_name}")
