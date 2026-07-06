"""
apps/yuanqi/patch.py — 元气打卡 VIP 补丁

补丁内容:
1. UserEntity.isVip() → return true
2. ServerUserType.isVip() → return true
3. ChinaHandle.b() → return true (核心 VIP 检查)
4. ChinaHandle.c() → 跳过登录检查，直接执行 callback
5. LaunchActivity.onCreate() → 写入假用户到 Room DB (模拟微信登录)
"""

import re
from pathlib import Path


def _replace_method_body(smali_path, method_sig, new_body):
    """替换 smali 方法体。"""
    text = smali_path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"(\.method.*?" + re.escape(method_sig) + r".*?\n)(.*?)(\.end method)",
        re.DOTALL,
    )
    m = pattern.search(text)
    if not m:
        print(f"  [WARN] Method not found: {method_sig}")
        return False
    text = text[: m.start(2)] + new_body + "\n" + m.group(3) + text[m.end(3) :]
    smali_path.write_text(text, encoding="utf-8")
    return True


def patch(smali_dir: Path, version_info: dict = None, repo_url: str = None, **kwargs) -> list[str]:
    changes = []
    VIP_TRUE = "    .locals 1\n    const/4 v0, 0x1\n    return v0"

    # 1-3. isVip() / ChinaHandle.b() → return true
    for name, path, sig in [
        ("UserEntity.isVip()", "com/habits/todolist/plan/wish/data/entity/UserEntity.smali", "isVip()Z"),
        ("ServerUserType.isVip()", "com/lp/diff/common/base/ServerUserType.smali", "isVip()Z"),
        ("ChinaHandle.b()", "com/lp/channel/china/ChinaHandle.smali", "b()Z"),
    ]:
        f = smali_dir / path
        if f.exists() and _replace_method_body(f, sig, VIP_TRUE):
            changes.append(f"{name} → return true")

    # 4. ChinaHandle.c() → 跳过登录检查
    china_handle = smali_dir / "com/lp/channel/china/ChinaHandle.smali"
    if china_handle.exists():
        text = china_handle.read_text(encoding="utf-8")
        old = (
            "    :cond_1\n"
            "    invoke-virtual {v0}, Lcom/lp/diff/common/data/BaseCHUserInfo;->getOpenId()Ljava/lang/String;\n"
        )
        new = (
            "    :cond_1\n"
            "    invoke-interface {p1}, Lh7/a;->e()V\n"
            "    return-void\n"
            "    invoke-virtual {v0}, Lcom/lp/diff/common/data/BaseCHUserInfo;->getOpenId()Ljava/lang/String;\n"
        )
        if old in text:
            china_handle.write_text(text.replace(old, new, 1), encoding="utf-8")
            changes.append("ChinaHandle.c() → 跳过登录检查")

    # 5. LaunchActivity.onCreate() → l.k() 写入假用户
    launch = smali_dir / "com/habits/todolist/plan/wish/ui/activity/LaunchActivity.smali"
    if launch.exists():
        text = launch.read_text(encoding="utf-8")
        # .locals 7 → 8
        text = text.replace(
            ".method public final onCreate(Landroid/os/Bundle;)V\n    .locals 7",
            ".method public final onCreate(Landroid/os/Bundle;)V\n    .locals 8",
            1,
        )
        # 在 return-void 前注入 l.k() 调用
        old_end = (
            "    invoke-static {p1, v1, v3, v2, v0}, LZ7/B;->m(LZ7/z;LI7/j;"
            "Lkotlinx/coroutines/CoroutineStart;LQ7/c;I)LZ7/l0;\n"
            "\n"
            "    .line 203\n"
            "    .line 204\n"
            "    .line 205\n"
            "    return-void\n"
            ".end method"
        )
        new_end = (
            "    invoke-static {p1, v1, v3, v2, v0}, LZ7/B;->m(LZ7/z;LI7/j;"
            "Lkotlinx/coroutines/CoroutineStart;LQ7/c;I)LZ7/l0;\n"
            "\n"
            "    .line 203\n"
            "    .line 204\n"
            "    .line 205\n"
            "\n"
            '    const-string v0, "VIP用户"\n'
            '    const-string v1, ""\n'
            '    const-string v2, "fake_openid_001"\n'
            '    const-string v3, "V"\n'
            "    invoke-static {v0, v1, v2, v3}, Lorg/sufficientlysecure/htmltextview/l;->k(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)V\n"
            "\n"
            "    return-void\n"
            ".end method"
        )
        if old_end in text:
            launch.write_text(text.replace(old_end, new_end, 1), encoding="utf-8")
            changes.append("LaunchActivity.onCreate() → l.k() 写入假用户")

    if changes:
        print("\n=== yuanqi VIP patch ===")
        for c in changes:
            print(f"  + {c}")
    return changes
