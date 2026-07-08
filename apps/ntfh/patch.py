"""
ntfh VIP patches
1. bt5.ʽ() → always return {"user-vip", "aXNQcmVtaXVt"}
2. User.getDisplayName() → return "VIP User" when null (data layer)
3. User.getUsername() → return "vip_user" when null (data layer)
4. ny1.smali → show "VIP User" when User object is null (UI fallback)
5. qs4.smali → skip premium card section
6. q1.smali → skip premium card rendering
"""
import sys
from pathlib import Path


def _patch_bt5(smali_dir: Path) -> str | None:
    bt5_path = smali_dir / "bt5.smali"
    if not bt5_path.exists():
        return "[WARN] bt5.smali not found"
    raw = bt5_path.read_bytes()
    target = b'\xca\xbd()Ljava/util/Set;'
    idx = raw.find(target)
    if idx < 0:
        return "[WARN] bt5.ʽ() not found"
    method_start = raw.rfind(b'.method', 0, idx)
    method_end = raw.find(b'.end method', idx) + len(b'.end method')
    new_method = (
        b'.method public final \xca\xbd()Ljava/util/Set;\n'
        b'    .locals 2\n'
        b'\n'
        b'    new-instance v0, Ljava/util/HashSet;\n'
        b'\n'
        b'    invoke-direct {v0}, Ljava/util/HashSet;-><init>()V\n'
        b'\n'
        b'    const-string v1, "user-vip"\n'
        b'\n'
        b'    invoke-interface {v0, v1}, Ljava/util/Set;->add(Ljava/lang/Object;)Z\n'
        b'\n'
        b'    const-string v1, "aXNQcmVtaXVt"\n'
        b'\n'
        b'    invoke-interface {v0, v1}, Ljava/util/Set;->add(Ljava/lang/Object;)Z\n'
        b'\n'
        b'    return-object v0\n'
        b'.end method'
    )
    new_raw = raw[:method_start] + new_method + raw[method_end:]
    bt5_path.write_bytes(new_raw)
    return "bt5.ʽ() -> hardcoded VIP roles"


def _patch_user(smali_dir: Path) -> list[str]:
    r = []
    path = smali_dir / "cn" / "skyrin" / "ntfh" / "core" / "model" / "data" / "User.smali"
    if not path.exists():
        return ["[WARN] User.smali not found"]
    text = path.read_text(encoding="utf-8")

    old1 = (
        '.method public final getDisplayName()Ljava/lang/String;\n'
        '    .locals 0\n'
        '\n'
        '    .line 1\n'
        '    iget-object p0, p0, Lcn/skyrin/ntfh/core/model/data/User;->displayName:Ljava/lang/String;\n'
        '\n'
        '    .line 2\n'
        '    .line 3\n'
        '    return-object p0\n'
        '.end method'
    )
    new1 = (
        '.method public final getDisplayName()Ljava/lang/String;\n'
        '    .locals 1\n'
        '\n'
        '    .line 1\n'
        '    iget-object v0, p0, Lcn/skyrin/ntfh/core/model/data/User;->displayName:Ljava/lang/String;\n'
        '\n'
        '    if-nez v0, :cond_ret\n'
        '\n'
        '    const-string v0, "VIP User"\n'
        '\n'
        '    :cond_ret\n'
        '    return-object v0\n'
        '.end method'
    )
    if old1 in text:
        text = text.replace(old1, new1)
        r.append("User.getDisplayName() -> \"VIP User\" when null")
    else:
        r.append("[WARN] getDisplayName() pattern not found (already patched?)")

    old2 = (
        '.method public final getUsername()Ljava/lang/String;\n'
        '    .locals 0\n'
        '\n'
        '    .line 1\n'
        '    iget-object p0, p0, Lcn/skyrin/ntfh/core/model/data/User;->username:Ljava/lang/String;\n'
        '\n'
        '    .line 2\n'
        '    .line 3\n'
        '    return-object p0\n'
        '.end method'
    )
    new2 = (
        '.method public final getUsername()Ljava/lang/String;\n'
        '    .locals 1\n'
        '\n'
        '    .line 1\n'
        '    iget-object v0, p0, Lcn/skyrin/ntfh/core/model/data/User;->username:Ljava/lang/String;\n'
        '\n'
        '    if-nez v0, :cond_ret\n'
        '\n'
        '    const-string v0, "vip_user"\n'
        '\n'
        '    :cond_ret\n'
        '    return-object v0\n'
        '.end method'
    )
    if old2 in text:
        text = text.replace(old2, new2)
        r.append("User.getUsername() -> \"vip_user\" when null")
    else:
        r.append("[WARN] getUsername() pattern not found (already patched?)")

    path.write_text(text, encoding="utf-8")
    return r


def _patch_ny1(smali_dir: Path) -> list[str]:
    r = []
    path = smali_dir / "ny1.smali"
    if not path.exists():
        return ["[WARN] ny1.smali not found"]
    text = path.read_text(encoding="utf-8")
    # displayName UI fallback
    old1 = (
        '    if-nez v8, :cond_4\n'
        '\n'
        '    .line 114\n'
        '    .line 115\n'
        '    const v6, -0x49119f9b\n'
        '\n'
        '    .line 116\n'
        '    .line 117\n'
        '    .line 118\n'
        '    const v8, 0x7f110471\n'
        '\n'
        '    .line 119\n'
        '    .line 120\n'
        '    .line 121\n'
        '    invoke-static {v4, v6, v8, v4, v14}, Lko0;->ˎ(Lx02;IILx02;Z)Ljava/lang/String;\n'
        '\n'
        '    .line 122\n'
        '    .line 123\n'
        '    .line 124\n'
        '    move-result-object v8\n'
        '\n'
        '    .line 125\n'
        '    goto :goto_1'
    )
    new1 = (
        '    if-nez v8, :cond_4\n'
        '\n'
        '    .line 114\n'
        '    .line 115\n'
        '    .line 116\n'
        '    .line 117\n'
        '    .line 118\n'
        '    const-string v8, "VIP User"\n'
        '\n'
        '    .line 125\n'
        '    goto :goto_1'
    )
    if old1 in text:
        text = text.replace(old1, new1)
        r.append("ny1 displayName -> VIP User")
    else:
        r.append("[WARN] ny1 displayName pattern not found")
    # username UI fallback
    old2 = (
        '    :cond_5\n'
        '    const-string v6, ""\n'
    )
    new2 = (
        '    :cond_5\n'
        '    const-string v6, "vip_user"\n'
    )
    if old2 in text:
        text = text.replace(old2, new2)
        r.append("ny1 username -> vip_user")
    else:
        r.append("[WARN] ny1 username pattern not found")
    path.write_text(text, encoding="utf-8")
    return r


def _patch_qs4(smali_dir: Path) -> str | None:
    path = smali_dir / "qs4.smali"
    if not path.exists():
        return "[WARN] qs4.smali not found"
    text = path.read_text(encoding="utf-8")
    if "    if-eqz v3, :cond_a" not in text:
        return "[WARN] qs4 premium check not found (already patched?)"
    text = text.replace("    if-eqz v3, :cond_a", "    goto :goto_9")
    path.write_text(text, encoding="utf-8")
    return "qs4 -> skip premium card section"


def _patch_q1(smali_dir: Path) -> str | None:
    path = smali_dir / "q1.smali"
    if not path.exists():
        return "[WARN] q1.smali not found"
    text = path.read_text(encoding="utf-8")
    if "    if-eqz v2, :cond_14" not in text:
        return "[WARN] q1 premium check not found (already patched?)"
    text = text.replace("    if-eqz v2, :cond_14", "    goto :goto_d")
    path.write_text(text, encoding="utf-8")
    return "q1 -> skip premium card rendering"


def patch(smali_dir: Path, *args, **kwargs) -> list[str]:
    results = []
    r = _patch_bt5(smali_dir)
    if r:
        results.append(r)
    results.extend(_patch_user(smali_dir))
    results.extend(_patch_ny1(smali_dir))
    r = _patch_qs4(smali_dir)
    if r:
        results.append(r)
    r = _patch_q1(smali_dir)
    if r:
        results.append(r)
    return results


if __name__ == "__main__":
    d = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("output/ntfh/apktool/smali")
    for r in patch(d):
        print(r)
